"""Pagination, filtering and ordering for Django admin inlines."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from django import forms
from django.contrib.admin.utils import lookup_spawns_duplicates
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import QuerySet
from django.db.models.constants import LOOKUP_SEP
from django.forms import BaseInlineFormSet, Form
from django.http import HttpRequest, QueryDict
from django.utils.translation import gettext_lazy as _

from django_admin_inline_controls.controls import (
    INFINITE,
    PAGES,
    InlineControls,
    OrderingValue,
    bound_primary_keys,
)

LOOKUP_LABELS = {
    "contains": _("contains"),
    "icontains": _("contains"),
    "startswith": _("starts with"),
    "istartswith": _("starts with"),
    "endswith": _("ends with"),
    "iendswith": _("ends with"),
    "gt": _("after"),
    "gte": _("from"),
    "lt": _("before"),
    "lte": _("to"),
    "in": _("in"),
    "isnull": _("is empty"),
    "year": _("year"),
    "month": _("month"),
    "day": _("day"),
}
TEXT_LOOKUPS = {
    "contains",
    "icontains",
    "startswith",
    "istartswith",
    "endswith",
    "iendswith",
    "iexact",
}
DATE_PART_LOOKUPS = {"year", "month", "day", "week_day", "quarter", "hour", "minute"}


def null_boolean_filter_field(**options: Any) -> forms.NullBooleanField:
    """Yes / No / any, where "any" is an empty value instead of "Unknown"."""
    choices = [("", "---------"), ("true", _("Yes")), ("false", _("No"))]
    return forms.NullBooleanField(widget=forms.Select(choices=choices), **options)


def resolve_lookup(
    model: type[models.Model], lookup: str
) -> tuple[models.Field | models.ForeignObjectRel, str | None]:
    """Split ``"author__name__icontains"`` into the ``name`` field and ``icontains``.

    Raises ``FieldDoesNotExist`` if the first part is not a field of ``model``.
    """
    parts = lookup.split(LOOKUP_SEP)
    opts = model._meta
    field: Any = None
    for index, part in enumerate(parts):
        try:
            field = opts.get_field(part)
        except FieldDoesNotExist:
            if field is None:
                raise
            return field, LOOKUP_SEP.join(parts[index:])
        if field.is_relation and field.related_model and index < len(parts) - 1:
            opts = field.related_model._meta
    return field, None


def build_filter_formfield(
    db_field: models.Field | models.ForeignObjectRel,
    lookup_name: str | None,
    label: str,
) -> forms.Field:
    """Return an optional form field suitable to filter by ``db_field``."""
    options: dict[str, Any] = {"required": False, "label": label}
    related_model = getattr(db_field, "related_model", None)
    choices = getattr(db_field, "flatchoices", None)
    if lookup_name == "isnull":
        return null_boolean_filter_field(**options)
    if lookup_name in DATE_PART_LOOKUPS:
        return forms.IntegerField(**options)
    if lookup_name == "in":
        if related_model is not None:
            return forms.ModelMultipleChoiceField(
                queryset=related_model._default_manager.all(), **options
            )
        if choices:
            return forms.MultipleChoiceField(choices=choices, **options)
        return forms.CharField(**options)
    if lookup_name in TEXT_LOOKUPS:
        return forms.CharField(**options)
    if related_model is not None:
        return forms.ModelChoiceField(
            queryset=related_model._default_manager.all(), **options
        )
    if choices:
        return forms.ChoiceField(choices=[("", "---------"), *choices], **options)
    if isinstance(db_field, models.BooleanField):
        return null_boolean_filter_field(**options)
    if isinstance(db_field, models.DateTimeField):
        return forms.DateTimeField(
            widget=forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            **options,
        )
    if isinstance(db_field, models.DateField):
        return forms.DateField(
            widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            **options,
        )
    formfield = (
        db_field.formfield(**options) if isinstance(db_field, models.Field) else None
    )
    return formfield or forms.CharField(**options)


class InlineControlsFormSetMixin:
    """Mixed into the inline's formset class by ``InlineControlsMixin``."""

    inline_controls_inline: InlineControlsMixin | None = None
    inline_controls_request: HttpRequest | None = None
    inline_controls_parent: Any = None

    prefix: str
    is_bound: bool

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        inline = self.inline_controls_inline
        request = self.inline_controls_request
        parent = self.inline_controls_parent
        self.inline_controls = (
            InlineControls(inline, request, parent, self.prefix)
            if inline is not None
            and request is not None
            and parent is not None
            and parent.pk is not None
            else None
        )

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()  # type: ignore[misc]
        if self.inline_controls is None:
            return queryset
        if not hasattr(self, "_inline_controls_queryset"):
            bound_pks = bound_primary_keys(self) if self.is_bound else None
            self._inline_controls_queryset = self.inline_controls.apply(
                queryset, bound_pks
            )
        return self._inline_controls_queryset


class InlineControlsMixin:
    """Add pagination, filters and sortable columns to an admin inline.

    Mix it in before ``TabularInline`` or ``StackedInline``::

        class BookInline(InlineControlsMixin, admin.TabularInline):
            model = Book
            inline_per_page = 20
            inline_ordering_fields = ["title", "published"]
            inline_filter_fields = ["status", "title__icontains"]
    """

    #: Rows per page. ``None`` disables pagination.
    inline_per_page: int | None = None
    #: ``"pages"`` renders page links, ``"infinite"`` loads more on scroll.
    inline_pagination: str = PAGES
    #: Sortable columns: field names, or ``{column: expression}`` where the
    #: expression is a field path, an ORM expression or an
    #: ``(ascending, descending)`` pair.
    inline_ordering_fields: Sequence[str] | Mapping[str, OrderingValue] = ()
    #: Ordering applied after the user's, before the ``pk`` tie-breaker.
    #: Defaults to the queryset's or the model's ordering.
    inline_default_ordering: Sequence[Any] = ()
    #: Filter lookups (``"status"``, ``"title__icontains"``,
    #: ``"published__gte"``). A form is generated from them unless
    #: ``inline_filter_form`` is set.
    inline_filter_fields: Sequence[str] = ()
    #: Custom filter form. Its fields are applied as lookups, unless
    #: ``inline_filter_fields`` restricts which ones.
    inline_filter_form: type[Form] | None = None
    #: Refresh the inline in place (fetch) instead of reloading the page.
    inline_controls_ajax: bool = True
    #: Wrapper template; it includes the inline's own ``template``.
    inline_controls_template = "django_admin_inline_controls/inline.html"

    # Provided by InlineModelAdmin.
    model: type[models.Model]
    template: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.inline_controls_inner_template = self.template
        self.template = self.inline_controls_template

    # Hooks -----------------------------------------------------------------

    def get_inline_per_page(self, request: HttpRequest, obj: Any) -> int | None:
        return self.inline_per_page

    def get_inline_ordering_fields(
        self, request: HttpRequest, obj: Any
    ) -> Sequence[str] | Mapping[str, OrderingValue]:
        return self.inline_ordering_fields

    def get_inline_filter_fields(self, request: HttpRequest, obj: Any) -> Sequence[str]:
        return self.inline_filter_fields

    def get_inline_filter_formfield(self, lookup: str) -> forms.Field:
        """Form field used to filter by ``lookup``. Override to customize one."""
        db_field, lookup_name = resolve_lookup(self.model, lookup)
        label = str(getattr(db_field, "verbose_name", db_field.name)).capitalize()
        if lookup_name in LOOKUP_LABELS:
            label = f"{label} ({LOOKUP_LABELS[lookup_name]})"
        return build_filter_formfield(db_field, lookup_name, label)

    def get_inline_filter_form_class(
        self, request: HttpRequest, obj: Any
    ) -> type[Form] | None:
        if self.inline_filter_form is not None:
            return self.inline_filter_form
        lookups = self.get_inline_filter_fields(request, obj)
        if not lookups:
            return None
        fields = {
            lookup: self.get_inline_filter_formfield(lookup) for lookup in lookups
        }
        return type("InlineFilterForm", (forms.Form,), fields)

    def get_inline_filter_form_kwargs(
        self, request: HttpRequest, obj: Any
    ) -> dict[str, Any]:
        """Extra keyword arguments for the filter form, e.g. the parent object."""
        return {}

    def get_inline_filtered_queryset(
        self,
        request: HttpRequest,
        obj: Any,
        queryset: QuerySet,
        data: QueryDict,
        prefix: str,
    ) -> tuple[Form | None, QuerySet]:
        """Return the bound filter form (or ``None``) and the filtered queryset."""
        form_class = self.get_inline_filter_form_class(request, obj)
        if form_class is None:
            return None, queryset
        form = form_class(
            data, prefix=prefix, **self.get_inline_filter_form_kwargs(request, obj)
        )
        form.is_valid()
        filters = {
            name: value
            for name, value in form.cleaned_data.items()
            if form[name].data not in (None, "", []) and value is not None
        }
        return form, self.filter_inline_queryset(request, queryset, filters)

    def filter_inline_queryset(
        self, request: HttpRequest, queryset: QuerySet, filters: dict[str, Any]
    ) -> QuerySet:
        """Apply the cleaned, non-empty filter values to ``queryset``.

        Override to handle form fields that are not plain lookups::

            def filter_inline_queryset(self, request, queryset, filters):
                if search := filters.pop("q", None):
                    queryset = queryset.filter(title__icontains=search)
                return super().filter_inline_queryset(request, queryset, filters)
        """
        allowed = set(self.inline_filter_fields) or set(filters)
        lookups = {name: value for name, value in filters.items() if name in allowed}
        queryset = queryset.filter(**lookups)
        if any(lookup_spawns_duplicates(self.model._meta, name) for name in lookups):
            queryset = queryset.distinct()
        return queryset

    # InlineModelAdmin ------------------------------------------------------

    def get_formset(
        self, request: HttpRequest, obj: Any = None, **kwargs: Any
    ) -> type[BaseInlineFormSet[Any, Any, Any]]:
        formset_class = super().get_formset(request, obj, **kwargs)  # type: ignore[misc]
        return type(
            formset_class.__name__,
            (InlineControlsFormSetMixin, formset_class),
            {
                "inline_controls_inline": self,
                "inline_controls_request": request,
                "inline_controls_parent": obj,
            },
        )

    @property
    def media(self) -> forms.Media:
        return super().media + forms.Media(  # type: ignore[misc]
            js=["django_admin_inline_controls/js/inline_controls.js"],
            css={"all": ["django_admin_inline_controls/css/inline_controls.css"]},
        )

    def check(self, **kwargs: Any) -> list[Any]:
        from django_admin_inline_controls.checks import check_inline_controls

        return [*super().check(**kwargs), *check_inline_controls(self)]  # type: ignore[misc]


__all__ = [
    "INFINITE",
    "PAGES",
    "InlineControlsFormSetMixin",
    "InlineControlsMixin",
]
