from decimal import Decimal

import pytest
from demo.models import Author, Book
from django.contrib import admin
from django.db import connection
from django.db.models import Avg, Count, Max, Sum
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation
from django.utils.html import format_html

from django_admin_inline_controls.controls import raw_number
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


def test_numbers_are_not_localized(get_request, author, settings):
    settings.USE_THOUSAND_SEPARATOR = True
    inline = make_inline(
        inline_footer_rows=[("All", {"pages": Sum("pages"), "title": Avg("pages")})]
    )
    Book.objects.filter(author=author, title="Book 25").update(pages=251)
    with translation.override("es"):
        rows = cells(controls(inline, get_request(), author).footer_rows)

    assert rows == [("All", {"pages": "3251", "title": "130.04"})]


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

    # Tabular inlines get a <tfoot>; the stacked one keeps the summary line.
    assert html.count('<tfoot class="inline-controls-tfoot">') == 2
    assert html.count("data-inline-controls-footer-rows") == 1
    assert 'data-column="pages"' in html


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

    assert 'data-value="4240">4240</span>' in html


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


# Values for the page's JS ---------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (3250, "3250"),
        (130.04, "130.04"),
        (Decimal("1234.50"), "1234.50"),
        (Decimal("1E+3"), "1000"),
        (None, ""),
        (True, ""),
        ("n/a", ""),
    ],
)
def test_raw_number(value, expected):
    assert raw_number(value) == expected


def test_raw_values_are_rendered_for_the_js(admin_client, author):
    url = reverse("admin:demo_author_change", args=[author.pk])
    with translation.override("es"):
        html = admin_client.get(url).content.decode()

    # Formatted text for people, raw digits for the page's JS.
    assert (
        'data-footer-key="1:pages" data-footer-row="Average" data-column="pages" '
        'data-value="130.0">130</span>'
    ) in html
    assert 'data-column="pages" data-value="3250">3250</span>' in html


# <tfoot> layout ---------------------------------------------------------------

from django_admin_inline_controls.controls import (  # noqa: E402
    FooterCell,
    FooterRow,
    InlineControls,
)

DJANGO = {"title": 1, "status": 2, "pages": 3}  # after th.original


def layout(request, rows, positions, width=0):
    state = InlineControls(make_inline(), request, None, "books")
    state.__dict__["footer_rows"] = [
        FooterRow(label, [FooterCell(c, c, v, v) for c, v in cells.items()])
        for label, cells in rows
    ]
    result = state.tfoot_rows(positions, width)
    if result is None:
        return None
    return [
        (
            row.label,
            row.label_colspan,
            [
                (s.cell.column if s.cell else None, s.key, s.label_here)
                for s in row.cells
            ],
            row.trailing,
        )
        for row in result
    ]


def test_tfoot_label_spans_the_columns_before_the_first_value(get_request):
    assert layout(get_request(), [("Avg", {"pages": "5"})], DJANGO, 5) == [
        ("Avg", 3, [("pages", "0:pages", False)], 1)
    ]


def test_tfoot_label_goes_into_the_first_column_value(get_request):
    assert layout(
        get_request(),
        [("Total", {"title": "9", "pages": "5"})],
        DJANGO,
        4,
    ) == [
        (
            "Total",
            0,
            [
                (None, "", False),  # the narrow "original" column
                ("title", "0:title", True),
                (None, "", False),
                ("pages", "0:pages", False),
            ],
            0,
        )
    ]


def test_tfoot_without_leading_columns(get_request):
    # Unfold: no "original" column, the first field's is the first one.
    positions = {"title": 0, "status": 1, "pages": 2}
    assert layout(get_request(), [("Sum", {"title": "9"})], positions, 4) == [
        ("Sum", 0, [("title", "0:title", True)], 3)
    ]
    assert layout(get_request(), [("Sum", {"pages": "5"})], positions, 4) == [
        ("Sum", 2, [("pages", "0:pages", False)], 1)
    ]


def test_tfoot_needs_every_value_column_in_the_table(get_request):
    assert layout(get_request(), [("T", {"hidden": "1"})], {"title": 1}) is None
    assert layout(get_request(), [("T", {})], {"title": 1}) == []


def test_header_columns():
    from django_admin_inline_controls.templatetags.inline_controls import (
        _header_columns,
    )

    django = (
        '<thead><tr><th class="original"></th>'
        '<th class="column-title required">Title</th>'
        '<th class="column-id hidden"></th>'
        '<th class="column-pages" colspan="2">Pages</th><th>Delete?</th></tr></thead>'
    )
    assert _header_columns(django) == ({"title": 1, "pages": 2}, 5)
    unfold = (
        '<thead class="hidden"><tr><th class="column-title x">T</th><th></th></tr>'
        "</thead>"
    )
    assert _header_columns(unfold) == ({"title": 0}, 2)
    assert _header_columns("<table></table>") == ({}, 0)


def test_tfoot_goes_after_the_table_own_tfoot():
    from django.template import Context, Engine

    from django_admin_inline_controls.templatetags import inline_controls

    class Controls:
        footer_rows = [FooterRow("Total", [FooterCell("title", "Title", "9", 9)])]
        tfoot_rendered = False

        def tfoot_rows(self, positions, width):
            return InlineControls.tfoot_rows(self, positions, width)

    class Opts:
        inline_footer_tfoot = True
        inline_footer_tfoot_template = "django_admin_inline_controls/tfoot.html"

    class FormSet:
        opts = Opts()

    engine = Engine(
        loaders=[
            (
                "django.template.loaders.locmem.Loader",
                {
                    "inner.html": (
                        '<table><thead><tr><th class="column-title"></th></tr></thead>'
                        '<tbody></tbody><tfoot class="own"></tfoot></table>'
                    )
                },
            ),
            "django.template.loaders.app_directories.Loader",
        ],
        libraries={"inline_controls": inline_controls.__name__},
    )
    template = engine.from_string(
        '{% load inline_controls %}{% inline_controls_render_inline "inner.html" %}'
    )
    controls = Controls()
    html = template.render(
        Context({"controls": controls, "inline_admin_formset": FormSet()})
    )
    assert html.index('class="own"') < html.index("inline-controls-tfoot")
    assert controls.tfoot_rendered


def test_tfoot_can_be_turned_off(admin_client, author, settings):
    from demo.admin import BookInline

    BookInline.inline_footer_tfoot = False
    try:
        url = reverse("admin:demo_author_change", args=[author.pk])
        html = admin_client.get(url).content.decode()
    finally:
        BookInline.inline_footer_tfoot = True

    # Only the articles' tfoot is left; the books' rows are a summary now.
    assert html.count('<tfoot class="inline-controls-tfoot">') == 1
    assert html.count("data-inline-controls-footer-rows") == 2


def test_custom_tfoot_template(admin_client, author):
    from demo.admin import BookInline

    BookInline.inline_footer_tfoot_template = "custom/tfoot.html"
    try:
        url = reverse("admin:demo_author_change", args=[author.pk])
        html = admin_client.get(url).content.decode()
    finally:
        BookInline.inline_footer_tfoot_template = (
            "django_admin_inline_controls/tfoot.html"
        )

    assert "<em>3250 pages</em>" in html


def test_check_tfoot_type():
    ids = [e.id for e in make_inline(inline_footer_tfoot="yes").check()]

    assert "admin_inline_controls.E017" in ids


# The add view ------------------------------------------------------------------


def test_add_view_renders_the_tfoot_without_values(admin_client, db):
    html = admin_client.get(reverse("admin:demo_author_add")).content.decode()

    # Books (two rows) and articles (one): the structure, no values.
    assert html.count('<tfoot class="inline-controls-tfoot">') == 2
    assert (
        'data-footer-key="0:pages" data-footer-row="Total" data-column="pages" '
        'data-value=""></span>'
    ) in html
    assert 'data-footer-key="1:pages" data-footer-row="Average"' in html
    assert 'data-footer-key="0:words" data-footer-row="Total"' in html
    # No controls, and the stacked inline (no table) gets no summary line.
    assert "data-inline-controls" not in html
    assert "inline-controls-footer-rows" not in html


def test_add_view_asks_the_hook_for_the_rows_with_no_object(get_request):
    from django_admin_inline_controls.controls import empty_footer_rows

    seen = []

    class Inline(InlineControlsMixin, admin.TabularInline):
        model = Book

        def get_inline_footer_rows(self, request, obj):
            seen.append(obj)
            return [("Total", {"pages": Sum("pages"), "not_a_field": Sum("pages")})]

    request = get_request()
    rows = empty_footer_rows(Inline(Author, admin.site), request)

    assert seen == [None]
    assert [
        (row.label, [(c.column, c.column_label, c.value, c.raw) for c in row.cells])
        for row in rows
    ] == [
        ("Total", [("pages", "Pages", "", ""), ("not_a_field", "not_a_field", "", "")])
    ]
    assert empty_footer_rows(make_inline(), request) == []


def test_add_view_without_the_tfoot(admin_client, db, settings):
    from demo.admin import ArticleInline, BookInline

    for inline in (BookInline, ArticleInline):
        inline.inline_footer_tfoot = False
    try:
        html = admin_client.get(reverse("admin:demo_author_add")).content.decode()
    finally:
        for inline in (BookInline, ArticleInline):
            inline.inline_footer_tfoot = True

    assert "inline-controls-tfoot" not in html
