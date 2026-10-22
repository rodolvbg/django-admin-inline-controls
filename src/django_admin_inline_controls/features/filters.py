"""Filters above the rows: a form generated from lookups, or your own."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib.admin.utils import lookup_spawns_duplicates
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.constants import LOOKUP_SEP
from django.utils.translation import gettext_lazy as _

from .base import InlineControlsBaseMixin

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.db.models import QuerySet
    from django.forms import Form
    from django.http import HttpRequest, QueryDict

    from django_admin_inline_controls.types import FilterResult

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


class InlineFiltersMixin(InlineControlsBaseMixin):
    """A filter form above the rows, generated from lookups or your own,
    its values kept in the URL."""

    #: Filter lookups (``"status"``, ``"title__icontains"``,
    #: ``"published__gte"``). A form is generated from them unless
    #: ``inline_filter_form`` is set.
    inline_filter_fields: Sequence[str] = ()
    #: Custom filter form. Its fields are applied as lookups, unless
    #: ``inline_filter_fields`` restricts which ones.
    inline_filter_form: type[Form] | None = None
    #: Search the filters by a relation (``"publisher"``, ``"tags__in"``) with
    #: the admin's autocomplete, like ``autocomplete_fields``: ``True`` for
    #: all of them, or a list of lookups. Needs a ``ModelAdmin`` with
    #: ``search_fields`` for the related model.
    inline_filter_autocomplete: bool | Sequence[str] = False
    #: Offer only the values the parent's rows use in the filters by choices
    #: or by a relation (not in autocomplete ones): ``True`` for all of them,
    #: or a list of lookups.
    inline_filter_only_used_values: bool | Sequence[str] = False
    #: Keep the filters behind a "Filters" button (with how many are on), as
    #: Unfold's ``list_filter_sheet``: ``True`` always, ``"narrow"`` only
    #: when the inline is narrow (a phone, a side column), ``False`` never.
    inline_filter_sheet: bool | str = False

    def get_inline_filter_sheet(self, request: HttpRequest, obj: Any) -> bool | str:
        return self.inline_filter_sheet

    def get_inline_filter_fields(self, request: HttpRequest, obj: Any) -> Sequence[str]:
        return self.inline_filter_fields

    def get_inline_filter_formfield(self, lookup: str) -> forms.Field:
        """Form field used to filter by ``lookup``. Override to customize one."""
        db_field, lookup_name = resolve_lookup(self.model, lookup)
        label = str(getattr(db_field, "verbose_name", db_field.name)).capitalize()
        if lookup_name in LOOKUP_LABELS:
            label = f"{label} ({LOOKUP_LABELS[lookup_name]})"
        formfield = build_filter_formfield(db_field, lookup_name, label)
        if self._filter_autocompletes(lookup, db_field, lookup_name):
            from django.contrib.admin.widgets import (
                AutocompleteSelect,
                AutocompleteSelectMultiple,
            )

            multiple = isinstance(formfield, forms.ModelMultipleChoiceField)
            widget_class = (
                AutocompleteSelectMultiple if multiple else AutocompleteSelect
            )
            formfield.widget = widget_class(db_field, self.admin_site)
        return formfield

    @staticmethod
    def _for_lookup(option: bool | Sequence[str], lookup: str) -> bool:
        return option is True or (not isinstance(option, bool) and lookup in option)

    def _filter_autocompletes(
        self, lookup: str, db_field: Any, lookup_name: str | None
    ) -> bool:
        """Whether the filter by ``lookup`` uses the admin's autocomplete."""
        if not self._for_lookup(self.inline_filter_autocomplete, lookup):
            return False
        if not isinstance(db_field, models.ForeignKey | models.ManyToManyField):
            return False
        if lookup_name not in (None, "exact", "in"):
            return False
        related_admin = self.admin_site._registry.get(db_field.related_model)
        return bool(related_admin and related_admin.get_search_fields(None))

    def _limit_filter_choices(self, form: Form, queryset: QuerySet) -> None:
        """Offer only the values ``queryset`` (the parent's rows) uses."""
        from django.contrib.admin.widgets import AutocompleteMixin

        for name, field in form.fields.items():
            if not self._for_lookup(self.inline_filter_only_used_values, name):
                continue
            if isinstance(field.widget, AutocompleteMixin):
                continue  # it searches every object
            try:
                _, lookup_name = resolve_lookup(self.model, name)
            except FieldDoesNotExist:
                continue
            path = (
                name.removesuffix(f"{LOOKUP_SEP}{lookup_name}") if lookup_name else name
            )
            if lookup_name not in (None, "exact", "in"):
                continue
            used = queryset.order_by().values(path)
            if isinstance(field, forms.ModelChoiceField):
                if field.queryset is not None:
                    field.queryset = field.queryset.filter(pk__in=used)
            elif isinstance(field, forms.ChoiceField):
                values = {str(value) for value in used.values_list(path, flat=True)}
                choices: list[tuple[Any, Any]] = list(field.choices)  # type: ignore[arg-type]
                field.choices = [
                    (value, label)
                    for value, label in choices
                    if value == "" or str(value) in values
                ]

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
    ) -> FilterResult:
        """Return the bound filter form (or ``None``) and the filtered queryset."""
        form_class = self.get_inline_filter_form_class(request, obj)
        if form_class is None:
            return None, queryset
        form = form_class(
            data, prefix=prefix, **self.get_inline_filter_form_kwargs(request, obj)
        )
        if self.inline_filter_only_used_values:
            self._limit_filter_choices(form, queryset)
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

    @property
    def media(self) -> forms.Media:
        media = super().media
        if self.inline_filter_autocomplete:
            # The autocomplete filters' select2 and admin scripts.
            for lookup in self.inline_filter_fields:
                try:
                    media += self.get_inline_filter_formfield(lookup).widget.media
                except FieldDoesNotExist:
                    continue  # reported by the checks
        return media
