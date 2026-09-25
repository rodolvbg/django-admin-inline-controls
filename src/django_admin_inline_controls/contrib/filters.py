"""django-filter integration. Requires the ``filters`` extra."""

from __future__ import annotations

from typing import Any

try:
    import django_filters
except ImportError as e:
    raise ImportError(
        "django_admin_inline_controls.contrib.filters requires django-filter. "
        "Install it with: pip install django-admin-inline-controls[filters]"
    ) from e

from django.db.models import QuerySet
from django.forms import Form
from django.http import HttpRequest, QueryDict

from django_admin_inline_controls.mixins import InlineControlsMixin


class FilterSetInlineControlsMixin(InlineControlsMixin):
    """Filter the inline with a django-filter ``FilterSet``::

        class BookInline(FilterSetInlineControlsMixin, admin.TabularInline):
            model = Book
            inline_per_page = 20
            inline_filterset_class = BookFilterSet

    The filterset receives the request (``self.request`` inside it) and
    whatever ``get_inline_filterset_kwargs()`` returns, e.g. the parent object.
    """

    inline_filterset_class: type[django_filters.FilterSet] | None = None

    def get_inline_filterset_class(
        self, request: HttpRequest, obj: Any
    ) -> type[django_filters.FilterSet] | None:
        return self.inline_filterset_class

    def get_inline_filterset_kwargs(
        self, request: HttpRequest, obj: Any
    ) -> dict[str, Any]:
        return {}

    def get_inline_filtered_queryset(
        self,
        request: HttpRequest,
        obj: Any,
        queryset: QuerySet,
        data: QueryDict,
        prefix: str,
    ) -> tuple[Form | None, QuerySet]:
        filterset_class = self.get_inline_filterset_class(request, obj)
        if filterset_class is None:
            return super().get_inline_filtered_queryset(
                request, obj, queryset, data, prefix
            )
        filterset = filterset_class(
            data,
            queryset=queryset,
            prefix=prefix,
            request=request,
            **self.get_inline_filterset_kwargs(request, obj),
        )
        return filterset.form, filterset.qs


__all__ = ["FilterSetInlineControlsMixin"]
