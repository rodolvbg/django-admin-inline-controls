"""Test-only admin site exercising options the demo admin doesn't use."""

from demo.models import Author, Book
from django import forms
from django.contrib import admin

from django_admin_inline_controls.mixins import (
    InlineControlsAdminMixin,
    InlineControlsMixin,
)

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


class CustomTemplatesBookInline(InlineControlsMixin, admin.TabularInline):
    """Every template extended, a few blocks overridden."""

    model = Book
    extra = 0
    fields = ["title"]
    verbose_name_plural = "custom books"
    inline_per_page = 5
    inline_filter_fields = ["status"]
    inline_controls_template = "custom/inline.html"
    inline_controls_toolbar_template = "custom/toolbar.html"
    inline_controls_footer_template = "custom/footer.html"


class PlainBookInline(InlineControlsMixin, admin.TabularInline):
    """No pagination, filters or ordering: must render like a normal inline."""

    model = Book
    extra = 0
    fields = ["title"]


class ThemedBookInline(InlineControlsMixin, admin.TabularInline):
    """A different inline markup, adapted to with inline_controls_selectors."""

    model = Book
    extra = 0
    can_delete = False
    fields = ["title", "pages"]
    verbose_name_plural = "themed books"
    template = "custom/themed_tabular.html"
    inline_per_page = 5
    inline_ordering_fields = ["pages"]
    inline_bulk_actions = ["delete_selected"]
    inline_controls_selectors = {
        "container": ".card",
        "heading": ".card-title",
        "table_head": "table.grid thead",
        "column_header": 'th[data-col="{name}"]',
        "row_label": ":scope > td.row-name > .label",
        "tabular_rows": "{group} table.grid tbody > tr.form-row",
    }


@admin.register(Author, site=site)
class AuthorAdmin(InlineControlsAdminMixin, admin.ModelAdmin):
    inlines = [
        CustomFormBookInline,
        PlainBookInline,
        CustomTemplatesBookInline,
        ThemedBookInline,
    ]


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
