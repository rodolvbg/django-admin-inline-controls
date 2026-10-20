import datetime

from demo.models import Article, Author, Book, Publisher
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect, AutocompleteSelectMultiple
from django.contrib.auth.models import User
from django.http import QueryDict
from django.test import SimpleTestCase, TestCase
from unittest_parametrize import ParametrizedTestCase, parametrize

from django_admin_inline_controls.mixins import InlineControlsMixin
from tests.test_inline_controls import change_url, formset


def make_inline(site=admin.site, **attrs):
    inline_class = type(
        "BookInline",
        (InlineControlsMixin, admin.TabularInline),
        {"model": Book, "__module__": __name__, **attrs},
    )
    return inline_class(Author, site)


def filter_form(inline, author, query=""):
    form, _ = inline.get_inline_filtered_queryset(
        None, author, Book.objects.filter(author=author), QueryDict(query), "f"
    )
    return form


class TestFilterAutocomplete(TestCase):
    """The inline_filter_autocomplete option."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        cls.author = Author.objects.create(name="Author")
        statuses = [Book.Status.DRAFT, Book.Status.PUBLISHED]
        Book.objects.bulk_create(
            Book(
                author=cls.author,
                title=f"Book {n:02d}",
                status=statuses[n % 2],
                published=datetime.date(2020, 1, 1) + datetime.timedelta(days=n),
                pages=10 * n,
                featured=n % 5 == 0,
            )
            for n in range(1, 26)
        )
        Article.objects.bulk_create(
            Article(author=cls.author, title=f"Article {n:02d}", words=n)
            for n in range(1, 21)
        )
        cls.used, cls.other, cls.unused = (
            Publisher.objects.create(name=name) for name in ("Used", "Other", "Unused")
        )
        books = list(Book.objects.filter(author=cls.author).order_by("pk"))
        for book in books[:10]:
            book.publisher = cls.used
        for book in books[10:12]:
            book.publisher = cls.other
        Book.objects.bulk_update(books, ["publisher"])
        # Used by another author's book only.
        Book.objects.create(
            author=Author.objects.create(name="Someone else"),
            title="Elsewhere",
            publisher=cls.unused,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_relation_filters_can_autocomplete(self):
        inline = make_inline(
            inline_filter_fields=[
                "publisher",
                "publisher__in",
                "status",
                "title__icontains",
            ],
            inline_filter_autocomplete=True,
        )
        form = filter_form(inline, self.author)

        assert type(form.fields["publisher"].widget) is AutocompleteSelect
        assert type(form.fields["publisher__in"].widget) is AutocompleteSelectMultiple
        # Not relations: their usual widgets.
        assert not isinstance(form.fields["status"].widget, AutocompleteSelect)
        assert not isinstance(
            form.fields["title__icontains"].widget, AutocompleteSelect
        )

    def test_autocomplete_only_listed_lookups_and_searchable_admins(self):
        listed = make_inline(
            inline_filter_fields=["publisher", "publisher__in"],
            inline_filter_autocomplete=["publisher"],
        )
        form = filter_form(listed, self.author)
        assert type(form.fields["publisher"].widget) is AutocompleteSelect
        assert not isinstance(
            form.fields["publisher__in"].widget, AutocompleteSelectMultiple
        )

        # No ModelAdmin with search_fields for Publisher on this site.
        site = admin.AdminSite(name="no_publisher_site")
        plain = make_inline(
            site, inline_filter_fields=["publisher"], inline_filter_autocomplete=True
        )
        assert not isinstance(
            filter_form(plain, self.author).fields["publisher"].widget,
            AutocompleteSelect,
        )

    def test_autocomplete_filter_renders_and_loads_its_scripts(self):
        html = self.client.get(change_url(self.author)).content.decode()

        assert 'name="books-f-publisher"' in html
        assert "admin-autocomplete" in html
        assert 'data-field-name="publisher"' in html
        assert "admin/js/autocomplete.js" in html
        # Still a filter of the inline, not a field of the change form.
        assert 'form="books-inline-controls-filters"' in html

    def test_autocomplete_filter_filters(self):
        response = self.client.get(
            change_url(self.author, f"books-f-publisher={self.other.pk}")
        )

        controls = formset(response, "books").inline_controls
        assert controls.filtered_queryset.count() == 2

    def test_autocomplete_edge_cases(self):
        # Other lookups of a relation keep their own field (Yes/No for isnull).
        inline = make_inline(
            inline_filter_fields=["publisher__isnull"], inline_filter_autocomplete=True
        )
        form = filter_form(inline, self.author)
        assert not isinstance(
            form.fields["publisher__isnull"].widget, AutocompleteSelect
        )

        # The media skip a lookup the checks report.
        broken = make_inline(
            inline_filter_fields=["publisher", "nope"], inline_filter_autocomplete=True
        )
        assert "admin/js/autocomplete.js" in str(broken.media)


class TestFilterOnlyUsedValues(TestCase):
    """The inline_filter_only_used_values option."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        cls.author = Author.objects.create(name="Author")
        statuses = [Book.Status.DRAFT, Book.Status.PUBLISHED]
        Book.objects.bulk_create(
            Book(
                author=cls.author,
                title=f"Book {n:02d}",
                status=statuses[n % 2],
                published=datetime.date(2020, 1, 1) + datetime.timedelta(days=n),
                pages=10 * n,
                featured=n % 5 == 0,
            )
            for n in range(1, 26)
        )
        Article.objects.bulk_create(
            Article(author=cls.author, title=f"Article {n:02d}", words=n)
            for n in range(1, 21)
        )
        cls.used, cls.other, cls.unused = (
            Publisher.objects.create(name=name) for name in ("Used", "Other", "Unused")
        )
        books = list(Book.objects.filter(author=cls.author).order_by("pk"))
        for book in books[:10]:
            book.publisher = cls.used
        for book in books[10:12]:
            book.publisher = cls.other
        Book.objects.bulk_update(books, ["publisher"])
        # Used by another author's book only.
        Book.objects.create(
            author=Author.objects.create(name="Someone else"),
            title="Elsewhere",
            publisher=cls.unused,
        )

    def test_only_used_values(self):
        Book.objects.filter(author=self.author).update(status=Book.Status.DRAFT)
        Book.objects.filter(author=self.author, title="Book 01").update(
            status=Book.Status.PUBLISHED
        )
        inline = make_inline(
            inline_filter_fields=["status", "status__in", "publisher", "publisher__in"],
            inline_filter_only_used_values=True,
        )
        form = filter_form(inline, self.author)

        assert [value for value, _ in form.fields["status"].choices] == [
            "",
            "draft",
            "published",
        ]
        assert [value for value, _ in form.fields["status__in"].choices] == [
            "draft",
            "published",
        ]
        assert set(form.fields["publisher"].queryset) == {self.used, self.other}
        assert set(form.fields["publisher__in"].queryset) == {self.used, self.other}

    def test_only_used_values_for_listed_lookups(self):
        inline = make_inline(
            inline_filter_fields=["status", "publisher"],
            inline_filter_only_used_values=["publisher"],
        )
        form = filter_form(inline, self.author)

        assert len(form.fields["status"].choices) == 4  # untouched
        assert form.fields["publisher"].queryset.count() == 2

    def test_only_used_values_rejects_an_unused_value(self):
        inline = make_inline(
            inline_filter_fields=["publisher"], inline_filter_only_used_values=True
        )
        form, queryset = inline.get_inline_filtered_queryset(
            None,
            self.author,
            Book.objects.filter(author=self.author),
            QueryDict(f"f-publisher={self.unused.pk}"),
            "f",
        )

        assert "publisher" in form.errors
        assert queryset.count() == 25  # ignored, as any invalid filter

    def test_only_used_values_skip_what_it_cannot_limit(self):
        from django import forms

        class CustomForm(forms.Form):
            q = forms.CharField(required=False)
            title__icontains = forms.CharField(required=False)
            # Its queryset is set later, by the form itself: left alone.
            publisher = forms.ModelChoiceField(queryset=None, required=False)

        custom = make_inline(
            inline_filter_form=CustomForm, inline_filter_only_used_values=True
        )
        form = filter_form(custom, self.author)
        assert set(form.fields) == {"q", "title__icontains", "publisher"}
        assert form.fields["publisher"].queryset is None

        # Autocomplete filters search every object: not limited.
        both = make_inline(
            inline_filter_fields=["publisher"],
            inline_filter_autocomplete=True,
            inline_filter_only_used_values=True,
        )
        assert filter_form(both, self.author).fields["publisher"].queryset.count() == 3


class TestFilterOptionChecks(ParametrizedTestCase, SimpleTestCase):
    """System checks of the filter options."""

    @parametrize(
        ("attrs", "error_id"),
        [
            ({"inline_filter_autocomplete": "x"}, "admin_inline_controls.E020"),
            ({"inline_filter_only_used_values": [1]}, "admin_inline_controls.E022"),
        ],
    )
    def test_invalid_option(self, attrs, error_id):
        assert error_id in [e.id for e in make_inline(**attrs).check()]

    def test_unknown_autocomplete_lookups_are_reported(self):
        bad = make_inline(inline_filter_autocomplete=["status", "nope", "publisher"])

        ids = [e.id for e in bad.check()]
        assert ids.count("admin_inline_controls.E021") == 2

    def test_valid_autocomplete_option_has_no_errors(self):
        assert make_inline(inline_filter_autocomplete=True).check() == []
