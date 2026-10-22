"""What every feature shares: the inline's templates, its formset, its
script, and the parent ``ModelAdmin``'s way to re-render one inline."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, cast

from django import forms
from django.http import Http404, HttpRequest, HttpResponse
from django.template.response import TemplateResponse

from django_admin_inline_controls.controls import (
    DEFAULT_SELECTORS,
    INFINITE,
    InlineControls,
    bound_primary_keys,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db import models
    from django.db.models import QuerySet
    from django.forms import BaseInlineFormSet

    from django_admin_inline_controls.mixins import InlineControlsMixin
    from django_admin_inline_controls.types import Selectors


class InlineControlsFormSetMixin:
    """Mixed into the inline's formset class by ``InlineControlsMixin``."""

    inline_controls_inline: Any = None
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


class InlineControlsBaseMixin:
    """The inline's side every feature shares: its templates (the toolbar
    and the footer around the inline's own), its formset, its core script,
    refreshing in place, and the selectors its JS finds the markup by."""

    #: Refresh the inline in place (fetch) instead of reloading the page.
    inline_controls_ajax: bool = True
    #: CSS selectors the JS uses to find its way in the inline's markup,
    #: merged over ``DEFAULT_SELECTORS``: set the keys that differ in your
    #: theme or inline template.
    inline_controls_selectors: Selectors = {}
    #: Wrapper template; it includes the inline's own ``template``, the
    #: toolbar and the footer. Each one can extend the library's and
    #: override its blocks.
    inline_controls_template = "django_admin_inline_controls/inline.html"
    inline_controls_toolbar_template = "django_admin_inline_controls/toolbar.html"
    inline_controls_footer_template = "django_admin_inline_controls/footer.html"

    # Provided by InlineModelAdmin.
    model: type[models.Model]
    parent_model: type[models.Model]
    admin_site: Any
    template: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.inline_controls_inner_template = self.template
        self.template = self.inline_controls_template

    def get_inline_controls_selectors(
        self, request: HttpRequest, obj: Any
    ) -> dict[str, list[str]]:
        """``DEFAULT_SELECTORS`` with ``inline_controls_selectors`` applied."""
        selectors = {key: list(value) for key, value in DEFAULT_SELECTORS.items()}
        for key, value in self.inline_controls_selectors.items():
            selectors[key] = [value] if isinstance(value, str) else list(value)
        return selectors

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

    def get_inline_controls_scripts(self) -> list[str]:
        """The inline's scripts: the core one, then each feature's when it's
        on (see their mixins), always in the same order."""
        return ["django_admin_inline_controls/js/core.js"]

    @property
    def media(self) -> forms.Media:
        # One list, so several inlines' media merge cleanly (each one's
        # order is a constraint of the merge).
        return super().media + forms.Media(  # type: ignore[misc]
            js=self.get_inline_controls_scripts(),
            css={"all": ["django_admin_inline_controls/css/core.css"]},
        )

    def check(self, **kwargs: Any) -> list[Any]:
        from django_admin_inline_controls.checks import check_inline_controls

        inline = cast("InlineControlsMixin", self)
        return [*super().check(**kwargs), *check_inline_controls(inline)]  # type: ignore[misc]


class InlineControlsAdminBase:
    """The parent ``ModelAdmin``'s side every endpoint shares: finding an
    inline by its prefix, and answering with it re-rendered."""

    inline_controls_response_template = (
        "django_admin_inline_controls/inline_response.html"
    )

    # Provided by ModelAdmin.
    model: type[models.Model]
    admin_site: Any
    opts: Any

    def _inline_controls_url_name(self) -> str:
        opts = self.model._meta
        return f"{opts.app_label}_{opts.model_name}_inline_controls"

    def _inline_controls_formset_class(
        self,
        request: HttpRequest,
        obj: models.Model,
        prefix: str,
        enabled: Callable[[Any], bool],
    ) -> tuple[Any, Any]:
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
        inline: Any,
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
        inline: Any,
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
            queryset=inline.get_queryset(request),
        )
