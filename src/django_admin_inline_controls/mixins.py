"""Pagination, filtering and ordering for Django admin inlines.

``InlineControlsMixin`` (the inline's) and ``InlineControlsAdminMixin`` (the
parent ``ModelAdmin``'s) put the features together, one mixin each in
``django_admin_inline_controls.features``.
"""

from __future__ import annotations

from django_admin_inline_controls.controls import INFINITE, PAGES
from django_admin_inline_controls.features.base import (
    InlineControlsAdminBase,
    InlineControlsBaseMixin,
    InlineControlsFormSetMixin,
)
from django_admin_inline_controls.features.bulk_actions import (
    InlineActionSpec,
    InlineBulkActionsAdminMixin,
    InlineBulkActionsMixin,
)
from django_admin_inline_controls.features.filters import (
    DATE_PART_LOOKUPS,
    LOOKUP_LABELS,
    TEXT_LOOKUPS,
    InlineFiltersMixin,
    build_filter_formfield,
    null_boolean_filter_field,
    resolve_lookup,
)
from django_admin_inline_controls.features.ordering import InlineOrderingMixin
from django_admin_inline_controls.features.pagination import InlinePaginationMixin
from django_admin_inline_controls.features.save import (
    InlineSaveAdminMixin,
    InlineSaveMixin,
)


class InlineControlsMixin(
    InlineFiltersMixin,
    InlineBulkActionsMixin,
    InlineSaveMixin,
    InlinePaginationMixin,
    InlineOrderingMixin,
):
    """Add pagination, filters and sortable columns to an admin inline.

    Mix it in before ``TabularInline`` or ``StackedInline``::

        class BookInline(InlineControlsMixin, admin.TabularInline):
            model = Book
            inline_per_page = 20
            inline_ordering_fields = ["title", "published"]
            inline_filter_fields = ["status", "title__icontains"]

    Internally each feature is a mixin of its own, with its options and its
    script (added to ``media`` only when it's on; they don't work on their own,
    use this class): ``InlinePaginationMixin``
    (``inline_per_page``, ``inline_pagination``), ``InlineOrderingMixin``
    (``inline_ordering_fields``, ``inline_default_ordering``),
    ``InlineFiltersMixin`` (``inline_filter_*``), ``InlineSaveMixin``
    (``inline_save_button``) and ``InlineBulkActionsMixin``
    (``inline_bulk_actions``), over ``InlineControlsBaseMixin`` (the
    templates, ``inline_controls_ajax``, ``inline_controls_selectors``).
    """


class InlineControlsAdminMixin(InlineSaveAdminMixin, InlineBulkActionsAdminMixin):
    """Parent ``ModelAdmin`` side of ``inline_save_button`` and ``inline_bulk_actions``.

    Adds the endpoints that save a single inline and run inline actions,
    both returning the inline re-rendered::

        @admin.register(Author)
        class AuthorAdmin(InlineControlsAdminMixin, admin.ModelAdmin):
            inlines = [BookInline]

    Each one is a mixin of its own: ``InlineSaveAdminMixin`` and
    ``InlineBulkActionsAdminMixin``.
    """


__all__ = [
    "DATE_PART_LOOKUPS",
    "INFINITE",
    "LOOKUP_LABELS",
    "PAGES",
    "TEXT_LOOKUPS",
    "InlineActionSpec",
    "InlineBulkActionsAdminMixin",
    "InlineBulkActionsMixin",
    "InlineControlsAdminBase",
    "InlineControlsAdminMixin",
    "InlineControlsBaseMixin",
    "InlineControlsFormSetMixin",
    "InlineControlsMixin",
    "InlineFiltersMixin",
    "InlineOrderingMixin",
    "InlinePaginationMixin",
    "InlineSaveAdminMixin",
    "InlineSaveMixin",
    "build_filter_formfield",
    "null_boolean_filter_field",
    "resolve_lookup",
]
