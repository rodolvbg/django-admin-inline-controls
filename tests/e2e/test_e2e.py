"""Real end-to-end tests: an actual Chromium against pytest-django's
``live_server``, exercising the JS and the server-side controls together on
the demo ``AuthorAdmin`` (paginated ``books``, infinite ``articles`` and the
stacked ``books-2`` inlines).
"""

import re

import pytest
from demo.models import Article, Book
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def change_page(live_server, page: Page, admin_user, author):
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(
        f"{live_server.url}/admin/login/?next=/admin/demo/author/{author.pk}/change/"
    )
    page.fill("#id_username", "admin")
    page.fill("#id_password", "password")
    page.click("input[type=submit]")
    expect(page.locator("#books-inline-controls")).to_be_visible()
    # Survives in-place updates, lost on a full page load.
    page.evaluate("window.__noReload = true")
    yield page
    # Close the browser before the database is flushed: a request still in
    # flight would otherwise hit the shared in-memory SQLite connection
    # mid-flush and break this or the next test.
    page.wait_for_load_state("networkidle")
    page.close()
    assert errors == []


def saved_rows(page: Page, prefix: str):
    return page.locator(f"#{prefix}-group tr.form-row.has_original")


def column_values(page: Page, prefix: str, field: str):
    return (
        saved_rows(page, prefix)
        .locator(f"td.field-{field} input")
        .evaluate_all("els => els.map(e => e.value)")
    )


def assert_not_reloaded(page: Page):
    assert page.evaluate("window.__noReload") is True


def test_sort_by_header(change_page: Page):
    page = change_page
    page.click("#books-group th.column-pages .inline-controls-sort-toggle")
    expect(page.locator("#books-group th.column-pages")).to_have_class(
        re.compile(r"\binline-controls-ascending\b")
    )
    page.click("#books-group th.column-pages .inline-controls-sort-toggle")
    expect(page.locator("#books-group th.column-pages")).to_have_class(
        re.compile(r"\binline-controls-descending\b")
    )

    assert [int(v) for v in column_values(page, "books", "pages")][:3] == [
        250,
        240,
        230,
    ]
    assert "books-o=-pages" in page.url
    assert_not_reloaded(page)

    page.click("#books-group th.column-pages .inline-controls-sort-remove")
    expect(
        page.locator("#books-group th.column-pages .inline-controls-sort-remove")
    ).to_have_count(0)
    assert "books-o" not in page.url


def test_filter_and_clear(change_page: Page):
    page = change_page
    page.select_option("#id_books-f-status", "published")
    page.fill("#id_books-f-title__icontains", "book 1")
    page.press("#id_books-f-title__icontains", "Enter")

    expect(page.locator("#books-inline-controls .inline-controls-count")).to_have_text(
        re.compile(r"^\s*5 results\s*$")
    )
    assert "books-f-status=published" in page.url
    assert_not_reloaded(page)

    page.click("#books-group [data-inline-controls-clear]")
    expect(page.locator("#books-inline-controls .inline-controls-count")).to_have_text(
        re.compile(r"^\s*25 results\s*$")
    )
    assert "books-f-" not in page.url


def test_paginate_then_add_and_save(change_page: Page, author):
    page = change_page
    page.click("#books-group a.inline-controls-page >> text=3")
    expect(page.locator("#books-group .inline-controls-current")).to_have_text("3")
    assert column_values(page, "books", "title")[0] == "Book 21"
    assert_not_reloaded(page)

    # The admin's own "Add another" still works after the swap.
    page.click("#books-group .add-row a")
    page.fill("input[name='books-5-title']", "Brand new")
    page.fill("input[name='books-4-title']", "Book 25 edited")
    page.click("input[name=_continue]")

    expect(page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert Book.objects.filter(author=author, title="Brand new").exists()
    assert Book.objects.filter(author=author, title="Book 25 edited").exists()
    assert Book.objects.filter(author=author).count() == 26


def test_infinite_scroll_loads_on_scroll(change_page: Page):
    page = change_page
    expect(saved_rows(page, "articles")).to_have_count(15)
    page.evaluate(
        "document.querySelector("
        "'#articles-inline-controls [data-inline-controls-more]').scrollIntoView()"
    )

    expect(saved_rows(page, "articles")).to_have_count(20)
    expect(
        page.locator("#articles-inline-controls .inline-controls-count")
    ).to_contain_text("Showing 20 of 20")
    expect(
        page.locator("#articles-inline-controls [data-inline-controls-more]")
    ).to_have_count(0)
    assert_not_reloaded(page)


def test_load_more_after_adding_a_row_then_save(change_page: Page, author):
    page = change_page
    # No auto-loading, so the row can be added before the next page arrives.
    page.add_init_script("delete window.IntersectionObserver")
    page.reload()
    expect(saved_rows(page, "articles")).to_have_count(15)

    page.click("#articles-group .add-row a")
    page.fill("input[name='articles-15-title']", "Unsaved new")
    page.click("#articles-inline-controls [data-inline-controls-more]")

    expect(saved_rows(page, "articles")).to_have_count(20)
    # The unsaved row was renumbered past the loaded ones.
    assert page.input_value("#id_articles-INITIAL_FORMS") == "20"
    assert page.input_value("#id_articles-TOTAL_FORMS") == "21"
    assert page.input_value("input[name='articles-20-title']") == "Unsaved new"
    assert page.input_value("input[name='articles-15-title']") == "Article 16"

    page.fill("input[name='articles-18-title']", "Loaded then edited")
    page.click("input[name=_continue]")

    expect(page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert Article.objects.filter(author=author).count() == 21
    assert Article.objects.filter(title="Unsaved new").exists()
    assert Article.objects.get(title="Loaded then edited").words == 19


def test_stacked_inline_sort_links(change_page: Page):
    page = change_page
    page.evaluate(
        "document.querySelectorAll('#books-2-group details')"
        ".forEach(d => d.open = true)"
    )
    page.click("#books-2-group .inline-controls-sort-toggle >> text=Pages")
    expect(page.locator("#books-2-group .inline-controls-ascending")).to_be_visible()
    page.click("#books-2-group .inline-controls-sort-toggle >> text=Pages")

    expect(page.locator("#books-2-group .inline-controls-descending")).to_be_visible()
    assert page.input_value("input[name='books-2-0-pages']") == "250"
    assert_not_reloaded(page)


def test_unsaved_changes_prompt(change_page: Page):
    page = change_page
    page.fill("input[name='books-0-title']", "Not saved")
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.click("#books-group a.inline-controls-page >> text=2")

    expect(page.locator("#books-group .inline-controls-current")).to_have_text("1")
    assert page.input_value("input[name='books-0-title']") == "Not saved"
