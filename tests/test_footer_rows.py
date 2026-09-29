from decimal import Decimal

import pytest
from django.contrib import admin
from django.db import connection
from django.db.models import Avg, Count, Max, Sum
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation
from django.utils.html import format_html

from demo.models import Author, Book
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
        state.footer_rows

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
