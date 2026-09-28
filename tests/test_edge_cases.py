"""Branches the request-level tests don't reach on their own."""

import pytest
from demo.models import Author, Book
from django.contrib import admin
from django.test import RequestFactory

from django_admin_inline_controls.mixins import InlineControlsMixin


@pytest.fixture
def get_request(admin_user):
    def make(data=None, method="get"):
        request = getattr(RequestFactory(), method)("/", data or {})
        request.user = admin_user
        return request

    return make


def make_inline(**attrs):
    inline_class = type(
        "BookInline",
        (InlineControlsMixin, admin.TabularInline),
        {"model": Book, "__module__": __name__, **attrs},
    )
    return inline_class(Author, admin.site)


def build_formset(inline, request, author, **kwargs):
    return inline.get_formset(request, author)(
        instance=author, prefix="books", **kwargs
    )


def test_explicit_pk_ordering_is_not_duplicated(get_request, author):
    inline = make_inline(inline_per_page=5, inline_default_ordering=["-pk"])
    formset = build_formset(inline, get_request(), author)

    order_by = formset.inline_controls._order_by(Book.objects.all())

    assert order_by == ["-pk"]
    assert formset.get_queryset()[0].title == "Book 25"


@pytest.mark.parametrize(
    ("default_ordering", "expected"),
    [
        ((), ["title", "pk"]),
        (["-id"], ["title", "-id"]),
        (["pages"], ["title", "pages", "pk"]),
    ],
)
def test_pk_tie_breaker(get_request, author, default_ordering, expected):
    inline = make_inline(
        inline_ordering_fields=["title"], inline_default_ordering=default_ordering
    )
    formset = build_formset(inline, get_request({"books-o": "title"}), author)

    assert formset.inline_controls._order_by(Book.objects.all()) == expected


def test_ordering_column_without_field_uses_its_name(get_request, author):
    inline = make_inline(inline_ordering_fields={"custom": "pages"})
    formset = build_formset(inline, get_request({"books-o": "-custom"}), author)
    formset.get_queryset()

    (column,) = formset.inline_controls.ordering_columns
    assert column.label == "custom"
    assert column.direction == "descending"


def test_unpaginated_inline_has_no_page_links(get_request, author):
    inline = make_inline(inline_ordering_fields=["pages"])
    formset = build_formset(inline, get_request(), author)
    formset.get_queryset()
    controls = formset.inline_controls

    assert controls.page_links == []
    assert controls.next_page_url is None
    assert controls.is_paginated is False
    assert controls.total_count is None
    assert len(formset.get_queryset()) == 25


def test_bound_formset_skips_missing_primary_keys(get_request, author):
    book = Book.objects.get(title="Book 03")
    data = {
        "books-TOTAL_FORMS": "2",
        "books-INITIAL_FORMS": "2",
        "books-0-id": "",
        "books-1-id": str(book.pk),
    }
    inline = make_inline(inline_per_page=5)
    formset = build_formset(inline, get_request(data, "post"), author, data=data)

    assert list(formset.get_queryset()) == [book]


def test_multi_valued_filter_lookup_is_distinct(get_request, author):
    # Every book of the author matches through each of its sibling books,
    # which would repeat rows without distinct().
    inline = make_inline(inline_filter_fields=["author__books__title__icontains"])
    request = get_request({"books-f-author__books__title__icontains": "book"})
    formset = build_formset(inline, request, author)

    assert formset.get_queryset().count() == 25


def test_filterset_kwargs_default_to_empty(get_request, author):
    django_filters = pytest.importorskip("django_filters")
    from django_admin_inline_controls.contrib.filters import (
        FilterSetInlineControlsMixin,
    )

    class BookFilterSet(django_filters.FilterSet):
        class Meta:
            model = Book
            fields = ["status"]

    class BookInline(FilterSetInlineControlsMixin, admin.TabularInline):
        model = Book
        inline_filterset_class = BookFilterSet

    inline = BookInline(Author, admin.site)
    formset = build_formset(inline, get_request({"books-f-status": "draft"}), author)

    assert inline.get_inline_filterset_kwargs(None, author) == {}
    assert formset.get_queryset().count() == 12


def test_nested_mixin_pages_mode_passes_checks():
    nested_admin = pytest.importorskip("nested_admin")
    from django_admin_inline_controls.contrib.nested import NestedInlineControlsMixin

    class BookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
        model = Book
        inline_per_page = 5

    assert BookInline(Author, admin.site).check() == []
