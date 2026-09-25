"""Test-only admin site exercising options the demo admin doesn't use."""

from demo.models import Author, Book
from django import forms
from django.contrib import admin

from django_admin_inline_controls.mixins import InlineControlsMixin

site = admin.AdminSite(name="test_admin")


class SearchForm(forms.Form):
    q = forms.CharField(required=False)
    status = forms.ChoiceField(
        required=False, choices=[("", "---"), *Book.Status.choices]
    )


class CustomFormBookInline(InlineControlsMixin, admin.TabularInline):
    model = Book
    extra = 0
    fields = ["title", "status"]
    inline_per_page = 5
    inline_filter_form = SearchForm
    inline_filter_fields = ["status"]

    def filter_inline_queryset(self, request, queryset, filters):
        if search := filters.get("q"):
            queryset = queryset.filter(title__icontains=search)
        return super().filter_inline_queryset(request, queryset, filters)


class PlainBookInline(InlineControlsMixin, admin.TabularInline):
    """No pagination, filters or ordering: must render like a normal inline."""

    model = Book
    extra = 0
    fields = ["title"]


@admin.register(Author, site=site)
class AuthorAdmin(admin.ModelAdmin):
    inlines = [CustomFormBookInline, PlainBookInline]


try:
    import nested_admin
except ImportError:  # the "nested" extra is not installed
    nested_site = None
else:
    from django_admin_inline_controls.contrib.nested import NestedInlineControlsMixin

    nested_site = admin.AdminSite(name="nested_test_admin")

    class NestedBookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
        model = Book
        extra = 0
        fields = ["title", "pages"]
        inline_per_page = 5
        inline_ordering_fields = ["pages"]

    @admin.register(Author, site=nested_site)
    class NestedAuthorAdmin(nested_admin.NestedModelAdmin):
        inlines = [NestedBookInline]
