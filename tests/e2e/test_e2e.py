"""Real end-to-end tests: an actual Chromium against pytest-django's
``live_server``, exercising the JS and the server-side controls together on
the demo ``AuthorAdmin`` (paginated ``books``, infinite ``articles`` and the
stacked ``books-2`` inlines).
"""

import re

import pytest
from demo.models import Article, Author, Book
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


def test_save_only_the_inline(change_page: Page, author):
    page = change_page
    page.click("#books-group a.inline-controls-page >> text=2")
    expect(page.locator("#books-group .inline-controls-current")).to_have_text("2")
    page.fill("#id_name", "Parent not saved")
    page.fill("input[name='books-0-title']", "Saved with the inline")
    page.fill("input[name='articles-0-title']", "Other inline not saved")
    page.click("#books-inline-controls [data-inline-controls-save]")

    expect(
        page.locator(
            "#books-inline-controls .inline-controls-save .inline-controls-status"
        )
    ).to_have_text("Saved.")
    expect(page.locator("#books-group .inline-controls-current")).to_have_text("2")
    assert_not_reloaded(page)
    # Other unsaved edits on the page are left alone.
    assert page.input_value("#id_name") == "Parent not saved"
    assert (
        page.input_value("input[name='articles-0-title']") == "Other inline not saved"
    )
    assert Book.objects.filter(author=author, title="Saved with the inline").exists()
    assert Author.objects.get(pk=author.pk).name == "Author"
    assert not Article.objects.filter(title="Other inline not saved").exists()

    # Leaving the page afterwards doesn't prompt for the saved inline.
    page.click("#books-group a.inline-controls-page >> text=1")
    expect(page.locator("#books-group .inline-controls-current")).to_have_text("1")


def test_save_inline_shows_errors(change_page: Page, author):
    page = change_page
    page.fill("input[name='books-0-title']", "Not saved")
    page.fill("input[name='books-1-pages']", "-1")
    page.click("#books-inline-controls [data-inline-controls-save]")

    expect(
        page.locator(
            "#books-inline-controls .inline-controls-save .inline-controls-status"
        )
    ).to_have_text("Please correct the errors below.")
    expect(page.locator("#books-group .errorlist")).to_have_count(1)
    # The submitted values are kept, so they can be fixed and saved again.
    assert page.input_value("input[name='books-0-title']") == "Not saved"
    assert not Book.objects.filter(title="Not saved").exists()

    page.fill("input[name='books-1-pages']", "5")
    page.click("#books-inline-controls [data-inline-controls-save]")
    expect(
        page.locator(
            "#books-inline-controls .inline-controls-save .inline-controls-status"
        )
    ).to_have_text("Saved.")
    assert Book.objects.filter(title="Not saved").exists()


def test_save_infinite_inline_after_loading_more(change_page: Page, author):
    page = change_page
    page.add_init_script("delete window.IntersectionObserver")
    page.reload()
    page.click("#articles-inline-controls [data-inline-controls-more]")
    expect(saved_rows(page, "articles")).to_have_count(20)
    page.fill("input[name='articles-18-title']", "From page two")
    page.click("#articles-inline-controls [data-inline-controls-save]")

    expect(
        page.locator(
            "#articles-inline-controls .inline-controls-save .inline-controls-status"
        )
    ).to_have_text("Saved.")
    expect(saved_rows(page, "articles")).to_have_count(20)
    assert Article.objects.get(title="From page two").words == 19


def test_inline_action_on_selected_rows(change_page: Page, author):
    page = change_page
    boxes = page.locator("#books-group .inline-controls-select")
    expect(boxes).to_have_count(10)
    boxes.nth(1).check()
    boxes.nth(3).check()
    selection = page.locator("#books-inline-controls [data-inline-controls-selection]")
    expect(selection).to_have_text("2 of 25 selected")

    page.select_option(
        "#books-inline-controls [data-inline-controls-action]", "mark_published"
    )
    page.click("#books-inline-controls [data-inline-controls-run]")

    status = page.locator(
        "#books-inline-controls .inline-controls-actions .inline-controls-status"
    )
    expect(status).to_have_text("2 books published.")
    assert_not_reloaded(page)
    assert set(
        Book.objects.filter(author=author, status="published").values_list(
            "title", flat=True
        )
    ) >= {"Book 02", "Book 04"}
    expect(selection).to_have_text("0 of 25 selected")


def test_inline_action_select_across_with_confirmation(change_page: Page, author):
    page = change_page
    page.click("#books-inline-controls .inline-controls-select-all")
    across = page.locator("#books-inline-controls [data-inline-controls-select-across]")
    expect(across).to_have_text("Select all 25")
    across.click()
    expect(
        page.locator("#books-inline-controls [data-inline-controls-selection]")
    ).to_have_text("All 25 selected")

    page.select_option(
        "#books-inline-controls [data-inline-controls-action]", "delete_selected"
    )
    dialogs = []
    page.once(
        "dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss())
    )
    page.click("#books-inline-controls [data-inline-controls-run]")
    page.wait_for_timeout(200)
    assert dialogs == ["Delete 25 selected books? This cannot be undone."]
    assert Book.objects.filter(author=author).count() == 25

    page.once("dialog", lambda dialog: dialog.accept())
    page.click("#books-inline-controls [data-inline-controls-run]")
    status = page.locator(
        "#books-inline-controls .inline-controls-actions .inline-controls-status"
    )
    expect(status).to_have_text("Deleted 25 books.")
    assert Book.objects.filter(author=author).count() == 0


def test_inline_action_download(change_page: Page):
    page = change_page
    page.locator("#books-group .inline-controls-select").nth(0).check()
    page.select_option(
        "#books-inline-controls [data-inline-controls-action]", "export_csv"
    )
    with page.expect_download() as download:
        page.click("#books-inline-controls [data-inline-controls-run]")

    assert download.value.suggested_filename == "books.csv"
    assert_not_reloaded(page)


def test_inline_action_requires_selection(change_page: Page):
    page = change_page
    page.select_option(
        "#books-inline-controls [data-inline-controls-action]", "mark_published"
    )
    page.click("#books-inline-controls [data-inline-controls-run]")

    status = page.locator(
        "#books-inline-controls .inline-controls-actions .inline-controls-status"
    )
    expect(status).to_contain_text("Items must be selected")


def test_rows_loaded_later_get_checkboxes(change_page: Page):
    page = change_page
    page.evaluate(
        "document.querySelector("
        "'#articles-inline-controls [data-inline-controls-more]').scrollIntoView()"
    )
    expect(saved_rows(page, "articles")).to_have_count(20)
    expect(page.locator("#articles-group .inline-controls-select")).to_have_count(20)


@pytest.fixture
def themed_page(live_server, page: Page, admin_user, author):
    """The test admin's inline with a theme-like markup (``books-4``)."""
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(
        f"{live_server.url}/admin/login/?next=/test-admin/demo/author/{author.pk}/change/"
    )
    page.fill("#id_username", "admin")
    page.fill("#id_password", "password")
    page.click("input[type=submit]")
    expect(page.locator("#books-4-inline-controls")).to_be_visible()
    page.evaluate("window.__noReload = true")
    yield page
    page.wait_for_load_state("networkidle")
    page.close()
    assert errors == []


def test_selectors_adapt_to_another_markup(themed_page: Page, author):
    page = themed_page
    card = page.locator("#books-4-group .card")
    # Toolbar right after the card's title, footer at the card's end.
    expect(card.locator(".card-title + .inline-controls-toolbar")).to_have_count(1)
    expect(card.locator(":scope > .inline-controls-footer")).to_have_count(1)
    # Sortable header found through the configured selector.
    header = page.locator('#books-4-group th[data-col="pages"]')
    header.locator(".inline-controls-sort-toggle").click()
    expect(page.locator('#books-4-group th[data-col="pages"]')).to_have_class(
        re.compile(r"\binline-controls-ascending\b")
    )
    assert "books-4-o=pages" in page.url
    assert page.evaluate("window.__noReload") is True
    # Django's "Add another" was re-initialized with the configured rows.
    expect(page.locator("#books-4-group .add-row")).to_have_count(1)

    # Row checkboxes sit in the configured label, and actions work.
    boxes = page.locator(
        "#books-4-group td.row-name > .label > .inline-controls-select"
    )
    expect(boxes).to_have_count(5)
    first_title = page.input_value(
        "#books-4-group tr.has_original input[name$='-title']"
    )
    boxes.first.check()
    page.select_option(
        "#books-4-inline-controls [data-inline-controls-action]", "delete_selected"
    )
    page.once("dialog", lambda dialog: dialog.accept())
    page.click("#books-4-inline-controls [data-inline-controls-run]")
    status = page.locator(
        "#books-4-inline-controls .inline-controls-actions .inline-controls-status"
    )
    expect(status).to_have_text("Deleted 1 book.")
    assert not Book.objects.filter(author=author, title=first_title).exists()


def test_footer_rows_follow_the_filters(change_page: Page):
    page = change_page
    tfoot = page.locator("#books-group tfoot.inline-controls-tfoot")
    expect(tfoot.locator("tr").first).to_contain_text("Total 25")
    expect(tfoot.locator("tr").first).to_contain_text("3250")
    expect(
        page.locator("#books-inline-controls [data-inline-controls-footer-rows]")
    ).to_be_hidden()

    page.select_option("#id_books-f-status", "published")
    page.click("#books-group [data-inline-controls-apply]")

    # 13 published books (odd n), pages 10 * n.
    expect(tfoot.locator("tr").first).to_contain_text("Total 13")
    expect(tfoot.locator("tr").first).to_contain_text("1690")
    assert_not_reloaded(page)


def test_stacked_inline_shows_the_footer_summary(change_page: Page):
    page = change_page
    page.evaluate(
        "document.querySelectorAll('#books-2-group details')"
        ".forEach(d => d.open = true)"
    )
    summary = page.locator(
        "#books-2-inline-controls [data-inline-controls-footer-rows]"
    )

    expect(summary).to_be_visible()
    expect(summary).to_contain_text("3250")
