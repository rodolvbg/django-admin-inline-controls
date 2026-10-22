"""InlineFiltersMixin: the form fields generated from lookups."""

from demo.models import Author, Book
from django import forms
from django.contrib import admin
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.test import SimpleTestCase
from unittest_parametrize import ParametrizedTestCase, parametrize

from django_admin_inline_controls.mixins import (
    InlineControlsMixin,
    build_filter_formfield,
    resolve_lookup,
)


def book_field(name):
    return Book._meta.get_field(name)


class TestResolveLookup(ParametrizedTestCase, SimpleTestCase):
    """Resolving a filter lookup to its model field."""

    @parametrize(
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
    def test_resolve_lookup(self, lookup, field_name, lookup_name):
        field, name = resolve_lookup(Book, lookup)

        assert field.name == field_name
        assert name == lookup_name

    def test_resolve_lookup_unknown_field(self):
        with self.assertRaises(FieldDoesNotExist):
            resolve_lookup(Book, "nope__icontains")


class TestBuildFilterFormfield(ParametrizedTestCase, SimpleTestCase):
    """Building the form field of a filter."""

    @parametrize(
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
    def test_build_filter_formfield(self, db_field, lookup_name, expected):
        formfield = build_filter_formfield(db_field, lookup_name, "Label")

        assert type(formfield) is expected
        assert formfield.required is False
        assert formfield.label == "Label"

    def test_choice_filter_has_empty_choice(self):
        formfield = build_filter_formfield(book_field("status"), None, "Status")

        assert formfield.choices[0] == ("", "---------")

    def test_boolean_filter_empty_means_any(self):
        formfield = build_filter_formfield(book_field("featured"), None, "Featured")

        assert formfield.clean("") is None
        assert formfield.clean("true") is True
        assert formfield.clean("false") is False


class TestInlineFilterFormClass(SimpleTestCase):
    """The generated filter form of an inline."""

    def test_generated_filter_labels(self):
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
