"""The features of the inline controls, one mixin each, for the inline
(``InlineControlsMixin`` puts them together) and for its parent ``ModelAdmin``
(``InlineControlsAdminMixin``).

They are how the code is organized, not separate public mixins: they share one
toolbar and footer and the system checks read every option, so use
``InlineControlsMixin`` / ``InlineControlsAdminMixin``, never one feature alone."""

from .base import InlineControlsAdminBase, InlineControlsBaseMixin
from .bulk_actions import InlineBulkActionsAdminMixin, InlineBulkActionsMixin
from .filters import InlineFiltersMixin
from .ordering import InlineOrderingMixin
from .pagination import InlinePaginationMixin
from .save import InlineSaveAdminMixin, InlineSaveMixin

__all__ = [
    "InlineBulkActionsAdminMixin",
    "InlineBulkActionsMixin",
    "InlineControlsAdminBase",
    "InlineControlsBaseMixin",
    "InlineFiltersMixin",
    "InlineOrderingMixin",
    "InlinePaginationMixin",
    "InlineSaveAdminMixin",
    "InlineSaveMixin",
]
