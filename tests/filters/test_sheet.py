"""inline_filter_sheet: the filters behind a "Filters" button."""

import re

import pytest
from demo.admin import BookStackedInline
from demo.models import Author, Book
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.utils import translation

pytestmark = pytest.mark.django_db


@pytest.fixture
def author():
    author = Author.objects.create(name="Author")
    Book.objects.create(author=author, title="A", status=Book.Status.PUBLISHED)
    return author


def stacked_inline(client, author, query=""):
    """The stacked books inline (inline_filter_sheet = "narrow")."""
    client.force_login(User.objects.create_superuser("admin"))
    html = client.get(f"/admin/demo/author/{author.pk}/change/{query}").content.decode()
    start = html.index('id="books-2-inline-controls"')
    return html[
        start : html.index("</details>", html.index("inline-controls-filters", start))
    ]


def test_the_filters_are_behind_a_button(client, author):
    html = stacked_inline(client, author)
    assert (
        '<details class="inline-controls-filter-sheet '
        'inline-controls-filter-sheet-narrow">' in html
    )
    assert re.search(
        r'<summary class="button inline-controls-filter-toggle">\s*Filters', html
    )
    assert "inline-controls-filter-count" not in html
    assert 'name="books-2-f-status"' in html


def test_the_button_says_how_many_are_on(client, author):
    html = stacked_inline(client, author, "?books-2-f-status=published")
    assert "inline-controls-filter-toggle-active" in html
    assert re.search(
        r'<span class="inline-controls-filter-count" title="1 filter on">1</span>', html
    )


def test_in_spanish(client, author):
    with translation.override("es"):
        html = stacked_inline(client, author, "?books-2-f-status=published")
    assert re.search(r"Filtros\s*<span", html)
    assert 'title="1 filtro activo"' in html


@pytest.mark.parametrize(
    "value, sheet", [(True, "always"), ("narrow", "narrow"), (False, None)]
)
def test_the_sheet_of_each_value(value, sheet, author, monkeypatch):
    from django.contrib import admin

    from django_admin_inline_controls.controls import InlineControls

    monkeypatch.setattr(BookStackedInline, "inline_filter_sheet", value)
    inline = BookStackedInline(Author, admin.site)
    request = RequestFactory().get("/")
    request.user = User(is_superuser=True)
    controls = InlineControls(inline, request, author, "books-2")
    assert controls.filter_sheet == sheet
