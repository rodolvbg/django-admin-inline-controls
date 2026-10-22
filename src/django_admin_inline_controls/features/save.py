"""A button that saves only the inline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import PermissionDenied
from django.db import router, transaction
from django.urls import URLPattern, path
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from .base import InlineControlsAdminBase, InlineControlsBaseMixin

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


class InlineSaveMixin(InlineControlsBaseMixin):
    """A button that saves only this inline. Needs ``InlineSaveAdminMixin``
    (or ``InlineControlsAdminMixin``) on the parent ``ModelAdmin``."""

    #: Show a button that saves only this inline. Requires
    #: ``InlineControlsAdminMixin`` on the parent ``ModelAdmin``.
    inline_save_button: bool = False

    def get_inline_controls_scripts(self) -> list[str]:
        scripts = super().get_inline_controls_scripts()
        if self.inline_save_button:
            scripts.append("django_admin_inline_controls/js/save.js")
        return scripts


class InlineSaveAdminMixin(InlineControlsAdminBase):
    """The parent ``ModelAdmin``'s endpoint that saves one inline and answers
    with it re-rendered."""

    def get_urls(self) -> list[URLPattern]:
        return [
            path(
                "<path:object_id>/inline-controls/<str:prefix>/save/",
                self.admin_site.admin_view(self.inline_controls_save_view),
                name=f"{self._inline_controls_url_name()}_save",
            ),
            *super().get_urls(),  # type: ignore[misc]
        ]

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
            inline.has_change_permission(request, obj)
            or inline.has_add_permission(request, obj)
            or inline.has_delete_permission(request, obj)
        ):
            raise PermissionDenied

        params = self.get_formset_kwargs(request, obj, inline, prefix)  # type: ignore[attr-defined]
        formset = formset_class(**params)
        if not inline.has_change_permission(request, obj):
            # As in the change view: view-only rows aren't in the POST data,
            # so skip their validation unless they were marked for deletion.
            can_delete = inline.has_delete_permission(request, obj)
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
