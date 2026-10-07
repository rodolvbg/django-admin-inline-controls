import pytest
from demo.models import Author, Book, Publisher
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect, AutocompleteSelectMultiple
from django.http import QueryDict

from django_admin_inline_controls.mixins import InlineControlsMixin
from tests.test_inline_controls import change_url, formset


@pytest.fixture
def publishers(author):
    used, other, unused = (
        Publisher.objects.create(name=name) for name in ("Used", "Other", "Unused")
    )
    books = list(Book.objects.filter(author=author).order_by("pk"))
    for book in books[:10]:
        book.publisher = used
    for book in books[10:12]:
        book.publisher = other
    Book.objects.bulk_update(books, ["publisher"])
    # Used by another author's book only.
    Book.objects.create(
        author=Author.objects.create(name="Someone else"),
        title="Elsewhere",
        publisher=unused,
    )
    return used, other, unused


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


# Autocomplete -----------------------------------------------------------------


def test_relation_filters_can_autocomplete(author, publishers):
    inline = make_inline(
        inline_filter_fields=[
            "publisher",
            "publisher__in",
            "status",
            "title__icontains",
        ],
        inline_filter_autocomplete=True,
    )
    form = filter_form(inline, author)

    assert type(form.fields["publisher"].widget) is AutocompleteSelect
    assert type(form.fields["publisher__in"].widget) is AutocompleteSelectMultiple
    # Not relations: their usual widgets.
    assert not isinstance(form.fields["status"].widget, AutocompleteSelect)
    assert not isinstance(form.fields["title__icontains"].widget, AutocompleteSelect)


def test_autocomplete_only_listed_lookups_and_searchable_admins(author, publishers):
    listed = make_inline(
        inline_filter_fields=["publisher", "publisher__in"],
        inline_filter_autocomplete=["publisher"],
    )
    form = filter_form(listed, author)
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
        filter_form(plain, author).fields["publisher"].widget, AutocompleteSelect
    )


def test_autocomplete_filter_renders_and_loads_its_scripts(
    admin_client, author, publishers
):
    html = admin_client.get(change_url(author)).content.decode()

    assert 'name="books-f-publisher"' in html
    assert "admin-autocomplete" in html
    assert 'data-field-name="publisher"' in html
    assert "admin/js/autocomplete.js" in html
    # Still a filter of the inline, not a field of the change form.
    assert 'form="books-inline-controls-filters"' in html


def test_autocomplete_filter_filters(admin_client, author, publishers):
    used, other, _ = publishers
    response = admin_client.get(change_url(author, f"books-f-publisher={other.pk}"))

    controls = formset(response, "books").inline_controls
    assert controls.filtered_queryset.count() == 2


# Only used values ----------------------------------------------------------------


def test_only_used_values(author, publishers):
    used, other, unused = publishers
    Book.objects.filter(author=author).update(status=Book.Status.DRAFT)
    Book.objects.filter(author=author, title="Book 01").update(
        status=Book.Status.PUBLISHED
    )
    inline = make_inline(
        inline_filter_fields=["status", "status__in", "publisher", "publisher__in"],
        inline_filter_only_used_values=True,
    )
    form = filter_form(inline, author)

    assert [value for value, _ in form.fields["status"].choices] == [
        "",
        "draft",
        "published",
    ]
    assert [value for value, _ in form.fields["status__in"].choices] == [
        "draft",
        "published",
    ]
    assert set(form.fields["publisher"].queryset) == {used, other}
    assert set(form.fields["publisher__in"].queryset) == {used, other}


def test_only_used_values_for_listed_lookups(author, publishers):
    inline = make_inline(
        inline_filter_fields=["status", "publisher"],
        inline_filter_only_used_values=["publisher"],
    )
    form = filter_form(inline, author)

    assert len(form.fields["status"].choices) == 4  # untouched
    assert form.fields["publisher"].queryset.count() == 2


def test_only_used_values_rejects_an_unused_value(author, publishers):
    _, _, unused = publishers
    inline = make_inline(
        inline_filter_fields=["publisher"], inline_filter_only_used_values=True
    )
    form, queryset = inline.get_inline_filtered_queryset(
        None,
        author,
        Book.objects.filter(author=author),
        QueryDict(f"f-publisher={unused.pk}"),
        "f",
    )

    assert "publisher" in form.errors
    assert queryset.count() == 25  # ignored, as any invalid filter


def test_only_used_values_skip_what_it_cannot_limit(author, publishers):
    from django import forms

    class CustomForm(forms.Form):
        q = forms.CharField(required=False)
        title__icontains = forms.CharField(required=False)
        # Its queryset is set later, by the form itself: left alone.
        publisher = forms.ModelChoiceField(queryset=None, required=False)

    custom = make_inline(
        inline_filter_form=CustomForm, inline_filter_only_used_values=True
    )
    form = filter_form(custom, author)
    assert set(form.fields) == {"q", "title__icontains", "publisher"}
    assert form.fields["publisher"].queryset is None

    # Autocomplete filters search every object: not limited.
    both = make_inline(
        inline_filter_fields=["publisher"],
        inline_filter_autocomplete=True,
        inline_filter_only_used_values=True,
    )
    assert filter_form(both, author).fields["publisher"].queryset.count() == 3


# Checks -----------------------------------------------------------------------


def test_filter_option_checks():
    ids = lambda inline: [e.id for e in inline.check()]  # noqa: E731

    assert "admin_inline_controls.E020" in ids(
        make_inline(inline_filter_autocomplete="x")
    )
    assert "admin_inline_controls.E022" in ids(
        make_inline(inline_filter_only_used_values=[1])
    )
    bad = make_inline(inline_filter_autocomplete=["status", "nope", "publisher"])
    assert ids(bad).count("admin_inline_controls.E021") == 2
    assert ids(make_inline(inline_filter_autocomplete=True)) == []


def test_autocomplete_edge_cases(author, publishers):
    # Other lookups of a relation keep their own field (Yes/No for isnull).
    inline = make_inline(
        inline_filter_fields=["publisher__isnull"], inline_filter_autocomplete=True
    )
    form = filter_form(inline, author)
    assert not isinstance(form.fields["publisher__isnull"].widget, AutocompleteSelect)

    # The media skip a lookup the checks report.
    broken = make_inline(
        inline_filter_fields=["publisher", "nope"], inline_filter_autocomplete=True
    )
    assert "admin/js/autocomplete.js" in str(broken.media)
