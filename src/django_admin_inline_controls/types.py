"""Type aliases used across the package."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, TypeAlias

from django.db.models import QuerySet
from django.db.models.expressions import BaseExpression
from django.forms import Form

if TYPE_CHECKING:
    from django_admin_inline_controls.mixins import InlineActionSpec

#: How a column is ordered: a field path, an ORM expression or an explicit
#: ``(ascending, descending)`` pair.
OrderingValue: TypeAlias = str | BaseExpression | tuple[Any, Any]
#: ``inline_ordering_fields``: column names, or ``{column: OrderingValue}``.
OrderingFields: TypeAlias = Sequence[str] | Mapping[str, OrderingValue]
#: The current ordering: ``(column, descending)`` pairs, primary first.
Ordering: TypeAlias = list[tuple[str, bool]]
#: What filtering returns: the bound filter form (if any) and the queryset.
FilterResult: TypeAlias = tuple[Form | None, QuerySet]
#: ``inline_controls_selectors``: CSS selector(s) per key, tried in order.
Selectors: TypeAlias = Mapping[str, str | Sequence[str]]
#: ``inline_footer_rows``: ``(label, {column: value})`` pairs, a value being
#: an aggregate (``Sum("pages")``), a ``callable(queryset)`` or a constant.
FooterRows: TypeAlias = Sequence[tuple[Any, Mapping[str, Any]]]
#: Actions available to a user, keyed by name.
InlineActions: TypeAlias = "dict[str, InlineActionSpec]"

__all__ = [
    "FilterResult",
    "FooterRows",
    "InlineActions",
    "Ordering",
    "OrderingFields",
    "OrderingValue",
    "Selectors",
]
