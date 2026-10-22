"""Sortable columns."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import InlineControlsBaseMixin

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.http import HttpRequest

    from django_admin_inline_controls.types import OrderingFields


class InlineOrderingMixin(InlineControlsBaseMixin):
    """Columns the user sorts by, in the headers or as links."""

    #: Sortable columns: field names, or ``{column: expression}`` where the
    #: expression is a field path, an ORM expression or an
    #: ``(ascending, descending)`` pair.
    inline_ordering_fields: OrderingFields = ()
    #: Ordering applied after the user's, before the ``pk`` tie-breaker.
    #: Defaults to the queryset's or the model's ordering.
    inline_default_ordering: Sequence[Any] = ()

    def get_inline_ordering_fields(
        self, request: HttpRequest, obj: Any
    ) -> OrderingFields:
        return self.inline_ordering_fields
