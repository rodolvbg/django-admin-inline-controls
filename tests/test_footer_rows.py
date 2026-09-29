import json
from decimal import Decimal

import pytest
from demo.models import Author, Book
from django.contrib import admin
from django.db import connection
from django.db.models import Avg, Count, F, Max, Q, Sum
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation
from django.utils.html import format_html

from django_admin_inline_controls.controls import live_footer_spec
from django_admin_inline_controls.mixins import InlineControlsMixin


def make_inline(**attrs):
    return type(
        "BookInline",
        (InlineControlsMixin, admin.TabularInline),
        {"model": Book, "__module__": __name__, "fields": ["title", "pages"], **attrs},
    )(Author, admin.site)


@pytest.fixture
def get_request(admin_user):
    def make(data=None):
        request = RequestFactory().get("/", data or {})
        request.user = admin_user
        return request

    return make


def controls(inline, request, author):
    formset = inline.get_formset(request, author)(instance=author, prefix="books")
    formset.get_queryset()
    return formset.inline_controls


def cells(rows):
    return [
        (row.label, {cell.column: cell.value for cell in row.cells}) for row in rows
    ]


def test_aggregates_over_the_filtered_rows_on_every_page(get_request, author):
    inline = make_inline(
        inline_per_page=5,
        inline_filter_fields=["status"],
        inline_footer_rows=[
            ("Total", {"title": Count("pk"), "pages": Sum("pages")}),
            ("Max", {"pages": Max("pages")}),
        ],
    )
    # 13 published books: n = 1, 3, …, 25 → pages 10, 30, …, 250.
    rows = controls(inline, get_request({"books-f-status": "published"}), author)

    assert cells(rows.footer_rows) == [
        ("Total", {"title": "13", "pages": "1690"}),
        ("Max", {"pages": "250"}),
    ]


def test_page_scope_adds_up_the_shown_rows(get_request, author):
    inline = make_inline(
        inline_per_page=5,
        inline_footer_scope="page",
        inline_footer_rows=[("Total", {"pages": Sum("pages")})],
    )
    rows = controls(inline, get_request({"books-page": "2"}), author).footer_rows

    assert cells(rows) == [("Total", {"pages": str(sum(10 * n for n in range(6, 11)))})]


def test_all_aggregates_run_in_one_query(get_request, author):
    inline = make_inline(
        inline_footer_rows=[
            ("Total", {"title": Count("pk"), "pages": Sum("pages")}),
            ("Average", {"pages": Avg("pages")}),
        ],
    )
    state = controls(inline, get_request(), author)
    with CaptureQueriesContext(connection) as queries:
        rows = state.footer_rows

    assert len(rows) == 2
    assert len(queries) == 1


def test_callables_constants_and_formatting(get_request, author):
    inline = make_inline(
        inline_footer_rows=[
            (
                "Info",
                {
                    "title": lambda queryset: queryset.filter(featured=True).count(),
                    "pages": format_html("<b>{}</b>", "safe"),
                },
            ),
            ("Average", {"pages": Avg("pages")}),
            ("Empty", {"pages": None}),
        ],
    )
    rows = cells(controls(inline, get_request(), author).footer_rows)

    assert rows[0] == ("Info", {"title": "5", "pages": "<b>safe</b>"})
    assert rows[1] == ("Average", {"pages": "130"})
    assert rows[2] == ("Empty", {"pages": ""})


def test_numbers_are_localized(get_request, author):
    inline = make_inline(inline_footer_rows=[("Avg", {"pages": Avg("pages")})])
    Book.objects.filter(author=author, title="Book 25").update(pages=251)
    with translation.override("es"):
        rows = cells(controls(inline, get_request(), author).footer_rows)

    assert rows == [("Avg", {"pages": "130,04"})]


def test_format_hook(get_request, author):
    class Inline(InlineControlsMixin, admin.TabularInline):
        model = Book
        inline_footer_rows = [("Total", {"pages": Sum("pages")})]

        def format_inline_footer_value(self, column, value):
            return f"{value} p."

    rows = cells(
        controls(Inline(Author, admin.site), get_request(), author).footer_rows
    )

    assert rows == [("Total", {"pages": "3250 p."})]


def test_decimal_values_are_rounded(get_request, author):
    inline = make_inline()

    assert inline.format_inline_footer_value("x", Decimal("1.2345")) == "1.23"
    assert inline.format_inline_footer_value("x", 2.0) == "2"


def test_no_rows_no_footer(get_request, author):
    state = controls(make_inline(), get_request(), author)

    assert state.footer_rows == []
    assert state.has_footer is False


def test_footer_rows_render_and_count_for_the_footer(admin_client, author):
    url = reverse("admin:demo_author_change", args=[author.pk])
    html = admin_client.get(url).content.decode()

    assert "data-inline-controls-footer-rows" in html
    assert 'data-column="pages"' in html
    # The stacked inline has its own total.
    assert html.count('data-label="Total"') == 3


def test_footer_rows_follow_saving_the_inline(admin_client, author):
    from tests.test_inline_controls import post_data

    books = list(Book.objects.filter(author=author).order_by("pk")[:10])
    books[0].pages = 1000
    data = {
        k: v
        for k, v in post_data(author, books=books).items()
        if k.startswith("books-")
    }
    url = reverse("admin:demo_author_inline_controls_save", args=[author.pk, "books"])
    html = admin_client.post(url, data).content.decode()

    assert '<span class="inline-controls-footer-value">4240</span>' in html


@pytest.mark.parametrize(
    ("attrs", "error_id"),
    [
        ({"inline_footer_rows": "total"}, "admin_inline_controls.E013"),
        ({"inline_footer_rows": [("Total",)]}, "admin_inline_controls.E013"),
        ({"inline_footer_rows": [("Total", ["pages"])]}, "admin_inline_controls.E013"),
        (
            {"inline_footer_rows": [("Total", {"nope": Sum("pages")})]},
            "admin_inline_controls.E014",
        ),
        ({"inline_footer_scope": "all"}, "admin_inline_controls.E015"),
        (
            {
                "inline_footer_scope": "page",
                "inline_pagination": "infinite",
                "inline_per_page": 5,
            },
            "admin_inline_controls.E016",
        ),
    ],
)
def test_invalid_footer_configuration(attrs, error_id):
    assert error_id in [e.id for e in make_inline(**attrs).check()]


def test_valid_footer_configuration():
    inline = make_inline(
        inline_footer_rows=[("Total", {"pages": Sum("pages"), "title": Count("pk")})],
        inline_footer_scope="page",
    )

    assert not [e for e in inline.check() if e.id.startswith("admin_inline_controls")]


# Live footer ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Sum("pages"), {"fn": "sum", "field": "pages"}),
        (Avg("pages"), {"fn": "avg", "field": "pages"}),
        (Count("pk"), {"fn": "count", "field": None}),
        (Count("*"), {"fn": "count", "field": None}),
        (Count("published"), {"fn": "count", "field": "published"}),
        (Max("pages"), None),
        (Sum("pages", filter=Q(featured=True)), None),
        (Count("pages", distinct=True), None),
        (Sum("author__id"), None),
        (Sum(F("pages") * 2), None),
        (lambda queryset: 1, None),
        (42, None),
    ],
)
def test_live_spec(value, expected):
    assert live_footer_spec(value) == expected


def live_cells(state):
    return {
        (row.label, cell.column): cell.live
        for row in state.footer_rows
        for cell in row.cells
    }


def test_live_bases(get_request, author):
    inline = make_inline(
        inline_footer_live=True,
        inline_footer_rows=[
            ("Total", {"title": Count("pk"), "pages": Sum("pages")}),
            ("Average", {"pages": Avg("pages")}),
            ("Max", {"pages": Max("pages")}),
        ],
    )
    state = controls(inline, get_request(), author)
    with CaptureQueriesContext(connection) as queries:
        cells_ = live_cells(state)

    assert len(queries) == 1  # the average's sum and count come in the same query
    assert cells_ == {
        ("Total", "title"): {"fn": "count", "field": None, "base": 25},
        ("Total", "pages"): {"fn": "sum", "field": "pages", "base": 3250},
        ("Average", "pages"): {"fn": "avg", "field": "pages", "sum": 3250, "count": 25},
        ("Max", "pages"): None,
    }
    config = json.loads(state.config_json)
    assert config["footerLive"] is True
    assert config["numberFormat"] == {
        "language": "en-us",
        "decimal": ".",
        "thousands": ",",
        "grouping": False,
    }


def test_live_is_off_by_default_and_with_a_format_hook(get_request, author):
    rows = [("Total", {"pages": Sum("pages")})]

    class Formatted(InlineControlsMixin, admin.TabularInline):
        model = Book
        inline_footer_rows = rows
        inline_footer_live = True

        def format_inline_footer_value(self, column, value):
            return f"{value} p."

    off = controls(make_inline(inline_footer_rows=rows), get_request(), author)
    formatted = controls(Formatted(Author, admin.site), get_request(), author)

    for state in (off, formatted):
        assert live_cells(state) == {("Total", "pages"): None}
        assert json.loads(state.config_json)["footerLive"] is False


def test_live_number_format_follows_the_language(get_request, author):
    inline = make_inline(
        inline_footer_live=True, inline_footer_rows=[("T", {"pages": Sum("pages")})]
    )
    with translation.override("es"):
        config = json.loads(controls(inline, get_request(), author).config_json)

    assert config["numberFormat"]["language"] == "es"
    assert config["numberFormat"]["decimal"] == ","
    assert config["messages"]["footerLive"] == "Incluye cambios sin guardar"


def test_live_spec_is_rendered_for_the_js(admin_client, author):
    url = reverse("admin:demo_author_change", args=[author.pk])
    html = admin_client.get(url).content.decode()

    assert 'data-footer-key="0:pages"' in html
    assert "&quot;fn&quot;: &quot;sum&quot;" in html


def test_check_live_type():
    ids = [e.id for e in make_inline(inline_footer_live="yes").check()]

    assert "admin_inline_controls.E017" in ids


def test_live_bases_of_an_empty_selection(get_request, author):
    inline = make_inline(
        inline_footer_live=True,
        inline_filter_fields=["title__icontains"],
        inline_footer_rows=[("T", {"pages": Sum("pages"), "title": Avg("pages")})],
    )
    request = get_request({"books-f-title__icontains": "nothing matches"})

    assert live_cells(controls(inline, request, author)) == {
        ("T", "pages"): {"fn": "sum", "field": "pages", "base": 0},
        ("T", "title"): {"fn": "avg", "field": "pages", "sum": 0, "count": 0},
    }
