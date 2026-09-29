"""Pagination, filtering and ordering for Django admin inlines."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from django import forms
from django.contrib import messages
from django.contrib.admin.utils import lookup_spawns_duplicates, model_format_dict
from django.core.exceptions import FieldDoesNotExist, PermissionDenied, ValidationError
from django.db import models, router, transaction
from django.db.models import QuerySet
from django.db.models.constants import LOOKUP_SEP
from django.forms import BaseInlineFormSet, Form
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseBase,
    QueryDict,
)
from django.template.response import TemplateResponse
from django.urls import URLPattern, path
from django.utils.text import capfirst
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

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


class _KeepMissing(dict):
    def __missing__(self, key: str) -> str:
        return f"%({key})s"


@dataclass(frozen=True)
class InlineActionSpec:
    name: str
    function: Callable[..., Any]
    description: str
    confirmation: str | None


class InlineControlsFormSetMixin:
    """Mixed into the inline's formset class by ``InlineControlsMixin``."""

    inline_controls_inline: InlineControlsMixin | None = None
    inline_controls_request: HttpRequest | None = None
    inline_controls_parent: Any = None
    #: Infinite mode: render this many pages at once (after saving the inline).
    inline_controls_pages_loaded: int | None = None

    prefix: str
    is_bound: bool

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        inline = self.inline_controls_inline
        request = self.inline_controls_request
        parent = self.inline_controls_parent
        self.inline_controls = (
            InlineControls(
                inline,
                request,
                parent,
                self.prefix,
                pages_loaded=self.inline_controls_pages_loaded,
            )
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
    #: Show a button that saves only this inline. Requires
    #: ``InlineControlsAdminMixin`` on the parent ``ModelAdmin``.
    inline_save_button: bool = False
    #: Actions for the selected rows, like ``ModelAdmin.actions``: method
    #: names, callables, or ``"delete_selected"``. Requires
    #: ``InlineControlsAdminMixin`` on the parent ``ModelAdmin``.
    inline_actions: Sequence[str | Callable[..., Any]] = ()
    #: Wrapper template; it includes the inline's own ``template``.
    inline_controls_template = "django_admin_inline_controls/inline.html"

    # Provided by InlineModelAdmin.
    model: type[models.Model]
    parent_model: type[models.Model]
    admin_site: Any
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

    # Actions ---------------------------------------------------------------

    def _resolve_inline_action(
        self, action: str | Callable[..., Any]
    ) -> tuple[str, Callable[..., Any]]:
        from django_admin_inline_controls.actions import BUILTIN_ACTIONS

        if callable(action):
            return action.__name__, action
        if not isinstance(action, str):
            raise AttributeError(action)
        if hasattr(type(self), action):
            return action, getattr(type(self), action)
        if action in BUILTIN_ACTIONS:
            return action, BUILTIN_ACTIONS[action]
        raise AttributeError(action)

    def get_inline_actions(
        self, request: HttpRequest, obj: Any
    ) -> dict[str, InlineActionSpec]:
        """Actions available to this user, keyed by name."""
        actions: dict[str, InlineActionSpec] = {}
        # Unknown placeholders (``%(count)s``) are left for the JS to fill.
        names = _KeepMissing(model_format_dict(self.model._meta))
        for action in self.inline_actions:
            name, func = self._resolve_inline_action(action)
            permissions = getattr(func, "allowed_permissions", ())
            if not all(
                getattr(self, f"has_{permission}_permission")(request, obj)
                for permission in permissions
            ):
                continue
            description = getattr(
                func, "short_description", capfirst(name.replace("_", " "))
            )
            confirmation = getattr(func, "confirmation", None)
            actions[name] = InlineActionSpec(
                name=name,
                function=func,
                description=str(description) % names,
                confirmation=None
                if confirmation is None
                else str(confirmation) % names,
            )
        return actions

    def message_user(
        self,
        request: HttpRequest,
        message: str,
        level: int = messages.INFO,
        extra_tags: str = "",
        fail_silently: bool = False,
    ) -> None:
        """Like ``ModelAdmin.message_user()``, for use in inline actions."""
        messages.add_message(
            request, level, message, extra_tags=extra_tags, fail_silently=fail_silently
        )

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


class InlineControlsAdminMixin:
    """Parent ``ModelAdmin`` side of ``inline_save_button`` and ``inline_actions``.

    Adds the endpoints that save a single inline and run inline actions,
    both returning the inline re-rendered::

        @admin.register(Author)
        class AuthorAdmin(InlineControlsAdminMixin, admin.ModelAdmin):
            inlines = [BookInline]
    """

    inline_controls_response_template = (
        "django_admin_inline_controls/inline_response.html"
    )

    # Provided by ModelAdmin.
    model: type[models.Model]
    admin_site: Any
    opts: Any

    def get_urls(self) -> list[URLPattern]:
        opts = self.model._meta
        name = f"{opts.app_label}_{opts.model_name}_inline_controls"
        return [
            path(
                "<path:object_id>/inline-controls/<str:prefix>/save/",
                self.admin_site.admin_view(self.inline_controls_save_view),
                name=f"{name}_save",
            ),
            path(
                "<path:object_id>/inline-controls/<str:prefix>/action/",
                self.admin_site.admin_view(self.inline_controls_action_view),
                name=f"{name}_action",
            ),
            *super().get_urls(),  # type: ignore[misc]
        ]

    def _inline_controls_formset_class(
        self,
        request: HttpRequest,
        obj: models.Model,
        prefix: str,
        enabled: Callable[[Any], bool],
    ) -> tuple[Any, InlineControlsMixin]:
        """Find the formset class and inline with ``prefix``, like the change
        view does (a repeated default prefix gets ``-2``, ``-3``...)."""
        seen: dict[str, int] = {}
        for formset_class, inline in self.get_formsets_with_inlines(request, obj):  # type: ignore[attr-defined]
            default = formset_class.get_default_prefix()
            seen[default] = seen.get(default, 0) + 1
            current = (
                default
                if seen[default] == 1 and default
                else (f"{default}-{seen[default]}")
            )
            if current == prefix:
                if not enabled(inline):
                    break
                return formset_class, inline
        raise Http404(f"No such inline: {prefix!r}.")

    def _inline_controls_object(self, request: HttpRequest, object_id: str) -> Any:
        request.current_app = self.admin_site.name
        obj = self.get_object(request, object_id)  # type: ignore[attr-defined]
        if obj is None:
            raise Http404
        return obj

    def _inline_controls_response(
        self,
        request: HttpRequest,
        obj: Any,
        inline: InlineControlsMixin,
        formset: Any,
        prefix: str,
        status: str,
        message: str,
    ) -> HttpResponse:
        inline_admin_formsets = self.get_inline_formsets(  # type: ignore[attr-defined]
            request, [formset], [inline], obj
        )
        return TemplateResponse(
            request,
            self.inline_controls_response_template,
            {
                "inline_admin_formsets": inline_admin_formsets,
                "prefix": prefix,
                "status": status,
                "message": message,
                "opts": self.opts,
                "original": obj,
                "change": True,
                "is_popup": False,
            },
        )

    def _inline_controls_fresh_formset(
        self,
        request: HttpRequest,
        obj: Any,
        inline: InlineControlsMixin,
        formset_class: Any,
        prefix: str,
        loaded: int,
    ) -> Any:
        """The inline as stored now; in infinite mode, as many pages as were
        loaded (``loaded`` rows)."""
        per_page = inline.get_inline_per_page(request, obj)
        if inline.inline_pagination == INFINITE and per_page:
            formset_class.inline_controls_pages_loaded = max(
                1, math.ceil(loaded / per_page)
            )
        return formset_class(
            instance=obj,
            prefix=prefix,
            queryset=inline.get_queryset(request),  # type: ignore[attr-defined]
        )

    # Save ------------------------------------------------------------------

    def inline_controls_save_view(
        self, request: HttpRequest, object_id: str, prefix: str
    ) -> HttpResponse:
        return require_POST(self._inline_controls_save)(request, object_id, prefix)

    def _inline_controls_save(
        self, request: HttpRequest, object_id: str, prefix: str
    ) -> HttpResponse:
        obj = self._inline_controls_object(request, object_id)
        if not self.has_change_permission(request, obj):  # type: ignore[attr-defined]
            raise PermissionDenied
        formset_class, inline = self._inline_controls_formset_class(
            request, obj, prefix, lambda inline: inline.inline_save_button
        )
        if not (
            inline.has_change_permission(request, obj)  # type: ignore[attr-defined]
            or inline.has_add_permission(request, obj)  # type: ignore[attr-defined]
            or inline.has_delete_permission(request, obj)  # type: ignore[attr-defined]
        ):
            raise PermissionDenied

        params = self.get_formset_kwargs(request, obj, inline, prefix)  # type: ignore[attr-defined]
        formset = formset_class(**params)
        if not inline.has_change_permission(request, obj):  # type: ignore[attr-defined]
            # As in the change view: view-only rows aren't in the POST data,
            # so skip their validation unless they were marked for deletion.
            can_delete = inline.has_delete_permission(request, obj)  # type: ignore[attr-defined]
            for index, form in enumerate(formset.initial_forms):
                deleted = f"{formset.prefix}-{index}-DELETE" in request.POST
                if not (can_delete and deleted):
                    form._errors = {}
                    form.cleaned_data = form.initial

        # save_formset() and construct_change_message() expect the parent's
        # form; only the inline was submitted, so it is an unchanged one.
        form = self.get_form(request, obj, change=True)(instance=obj)  # type: ignore[attr-defined]
        form.changed_data = []

        if not formset.is_valid():
            return self._inline_controls_response(
                request,
                obj,
                inline,
                formset,
                prefix,
                "invalid",
                gettext("Please correct the errors below."),
            )
        with transaction.atomic(using=router.db_for_write(self.model)):
            self.save_formset(request, form, formset, change=True)  # type: ignore[attr-defined]
            message = self.construct_change_message(request, form, [formset])  # type: ignore[attr-defined]
            if message:
                self.log_change(request, obj, message)  # type: ignore[attr-defined]
        fresh = self._inline_controls_fresh_formset(
            request, obj, inline, formset_class, prefix, formset.initial_form_count()
        )
        return self._inline_controls_response(
            request, obj, inline, fresh, prefix, "saved", gettext("Saved.")
        )

    # Actions ---------------------------------------------------------------

    def inline_controls_action_view(
        self, request: HttpRequest, object_id: str, prefix: str
    ) -> HttpResponseBase:
        return require_POST(self._inline_controls_action)(request, object_id, prefix)

    def _inline_controls_action(
        self, request: HttpRequest, object_id: str, prefix: str
    ) -> HttpResponseBase:
        obj = self._inline_controls_object(request, object_id)
        if not self.has_view_or_change_permission(request, obj):  # type: ignore[attr-defined]
            raise PermissionDenied
        formset_class, inline = self._inline_controls_formset_class(
            request, obj, prefix, lambda inline: bool(inline.inline_actions)
        )
        actions = inline.get_inline_actions(request, obj)
        action = actions.get(request.POST.get("action", ""))
        if action is None:
            return HttpResponseBadRequest("Unknown or forbidden action.")

        try:
            loaded = int(request.POST.get("_inline_controls_loaded") or 0)
        except ValueError:
            loaded = 0
        # The current filters come from the query string, as for the page.
        formset = formset_class(
            instance=obj,
            prefix=prefix,
            queryset=inline.get_queryset(request),  # type: ignore[attr-defined]
        )
        formset.get_queryset()
        queryset = formset.inline_controls.filtered_queryset
        if request.POST.get("select_across") != "1":
            pk_field = queryset.model._meta.pk
            pks = []
            for raw in request.POST.getlist("_selected_action"):
                try:
                    pks.append(pk_field.to_python(raw))
                except ValidationError:
                    continue
            queryset = queryset.filter(pk__in=pks)

        if not queryset.exists():
            status, text = (
                "error",
                gettext(
                    "Items must be selected in order to perform actions on them. "
                    "No items have been changed."
                ),
            )
        else:
            request.inline_controls_parent = obj  # type: ignore[attr-defined]
            response = action.function(inline, request, queryset)
            if isinstance(response, HttpResponseBase):
                return response
            sent = list(messages.get_messages(request))
            failed = any(message.level >= messages.ERROR for message in sent)
            status = "error" if failed else "done"
            text = " ".join(str(message) for message in sent) or gettext("Done.")

        fresh = self._inline_controls_fresh_formset(
            request, obj, inline, formset_class, prefix, loaded
        )
        return self._inline_controls_response(
            request, obj, inline, fresh, prefix, status, text
        )


__all__ = [
    "INFINITE",
    "PAGES",
    "InlineActionSpec",
    "InlineControlsAdminMixin",
    "InlineControlsFormSetMixin",
    "InlineControlsMixin",
]
