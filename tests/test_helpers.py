import pytest
from demo.models import Author, Book
from django import forms
from django.contrib import admin
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import F
from django.db.models.functions import Lower

from django_admin_inline_controls.controls import (
    normalize_ordering_fields,
    ordering_expression,
)
from django_admin_inline_controls.mixins import (
    InlineControlsMixin,
    build_filter_formfield,
    resolve_lookup,
)


@pytest.mark.parametrize(
    ("lookup", "field_name", "lookup_name"),
    [
        ("title", "title", None),
        ("title__icontains", "title", "icontains"),
        ("author__name", "name", None),
        ("author__name__startswith", "name", "startswith"),
        ("author__in", "author", "in"),
        ("published__year", "published", "year"),
    ],
)
def test_resolve_lookup(lookup, field_name, lookup_name):
    field, name = resolve_lookup(Book, lookup)

    assert field.name == field_name
    assert name == lookup_name


def test_resolve_lookup_unknown_field():
    with pytest.raises(FieldDoesNotExist):
        resolve_lookup(Book, "nope__icontains")


def book_field(name):
    return Book._meta.get_field(name)


@pytest.mark.parametrize(
    ("db_field", "lookup_name", "expected"),
    [
        (book_field("title"), None, forms.CharField),
        (book_field("title"), "icontains", forms.CharField),
        (book_field("status"), None, forms.ChoiceField),
        (book_field("status"), "in", forms.MultipleChoiceField),
        (book_field("title"), "in", forms.CharField),
        (book_field("author"), None, forms.ModelChoiceField),
        (book_field("author"), "in", forms.ModelMultipleChoiceField),
        (book_field("featured"), None, forms.NullBooleanField),
        (book_field("published"), None, forms.DateField),
        (book_field("published"), "isnull", forms.NullBooleanField),
        (book_field("published"), "year", forms.IntegerField),
        (models.DateTimeField(), "gte", forms.DateTimeField),
        (book_field("pages"), "gte", forms.IntegerField),
        (Author._meta.get_field("books"), None, forms.ModelChoiceField),
    ],
)
def test_build_filter_formfield(db_field, lookup_name, expected):
    formfield = build_filter_formfield(db_field, lookup_name, "Label")

    assert type(formfield) is expected
    assert formfield.required is False
    assert formfield.label == "Label"


def test_choice_filter_has_empty_choice():
    formfield = build_filter_formfield(book_field("status"), None, "Status")

    assert formfield.choices[0] == ("", "---------")


def test_boolean_filter_empty_means_any():
    formfield = build_filter_formfield(book_field("featured"), None, "Featured")

    assert formfield.clean("") is None
    assert formfield.clean("true") is True
    assert formfield.clean("false") is False


@pytest.mark.parametrize(
    ("value", "descending", "expected"),
    [
        ("title", False, "title"),
        ("title", True, "-title"),
        ("-title", False, "-title"),
        ("-title", True, "title"),
        (("a", "-b"), True, "-b"),
        (("a", "-b"), False, "a"),
    ],
)
def test_ordering_expression_strings(value, descending, expected):
    assert ordering_expression(value, descending) == expected


def test_ordering_expression_expressions():
    assert ordering_expression(Lower("title"), True) == Lower("title").desc()
    assert ordering_expression(Lower("title"), False) == Lower("title").asc()

    asc = F("published").asc(nulls_last=True)
    assert ordering_expression(asc, False) is asc
    reversed_ = ordering_expression(asc, True)
    assert reversed_.descending
    assert not asc.descending  # the declared expression is not mutated


def test_normalize_ordering_fields():
    assert normalize_ordering_fields(["a", "b"]) == {"a": "a", "b": "b"}
    assert normalize_ordering_fields({"a": "x"}) == {"a": "x"}


def test_generated_filter_labels():
    class Inline(InlineControlsMixin, admin.TabularInline):
        model = Book
        inline_filter_fields = ["title__icontains", "published__gte", "status"]

    inline = Inline(Author, admin.site)
    form_class = inline.get_inline_filter_form_class(None, None)

    assert [f.label for f in form_class.base_fields.values()] == [
        "Title (contains)",
        "Published (from)",
        "Status",
    ]
