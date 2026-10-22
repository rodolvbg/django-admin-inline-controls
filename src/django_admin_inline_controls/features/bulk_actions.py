"""Actions for the selected rows, like the changelist's."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.contrib.admin.utils import model_format_dict
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponseBadRequest, HttpResponseBase
from django.urls import URLPattern, path
from django.utils.text import capfirst
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from .base import InlineControlsAdminBase, InlineControlsBaseMixin

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from django_admin_inline_controls.types import InlineActions


class _KeepMissing(dict):
    def __missing__(self, key: str) -> str:
        return f"%({key})s"


@dataclass(frozen=True)
class InlineActionSpec:
    name: str
    function: Callable[..., Any]
    description: str
    confirmation: str | None


class InlineBulkActionsMixin(InlineControlsBaseMixin):
    """Checkboxes on the rows and an "Action:" menu for the selected ones.
    Needs ``InlineBulkActionsAdminMixin`` (or ``InlineControlsAdminMixin``)
    on the parent ``ModelAdmin``."""

    #: Actions for the selected rows, like ``ModelAdmin.actions``: method
    #: names, callables, or ``"delete_selected"``. Requires
    #: ``InlineControlsAdminMixin`` on the parent ``ModelAdmin``.
    inline_bulk_actions: Sequence[str | Callable[..., Any]] = ()

    def _resolve_inline_bulk_action(
        self, action: str | Callable[..., Any]
    ) -> tuple[str, Callable[..., Any]]:
        from django_admin_inline_controls.actions import BUILTIN_BULK_ACTIONS

        if callable(action):
            return action.__name__, action
        if not isinstance(action, str):
            raise AttributeError(action)
        if hasattr(type(self), action):
            return action, getattr(type(self), action)
        if action in BUILTIN_BULK_ACTIONS:
            return action, BUILTIN_BULK_ACTIONS[action]
        raise AttributeError(action)

    def get_inline_bulk_actions(self, request: HttpRequest, obj: Any) -> InlineActions:
        """Actions available to this user, keyed by name."""
        actions: InlineActions = {}
        # Unknown placeholders (``%(count)s``) are left for the JS to fill.
        names = _KeepMissing(model_format_dict(self.model._meta))
        for action in self.inline_bulk_actions:
            name, func = self._resolve_inline_bulk_action(action)
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

    def get_inline_controls_scripts(self) -> list[str]:
        scripts = super().get_inline_controls_scripts()
        if self.inline_bulk_actions:
            scripts.append("django_admin_inline_controls/js/actions.js")
        return scripts


class InlineBulkActionsAdminMixin(InlineControlsAdminBase):
    """The parent ``ModelAdmin``'s endpoint that runs an inline's action and
    answers with the inline re-rendered."""

    def get_urls(self) -> list[URLPattern]:
        return [
            path(
                "<path:object_id>/inline-controls/<str:prefix>/action/",
                self.admin_site.admin_view(self.inline_controls_action_view),
                name=f"{self._inline_controls_url_name()}_action",
            ),
            *super().get_urls(),  # type: ignore[misc]
        ]

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
            request,
            obj,
            prefix,
            lambda inline: bool(inline.inline_bulk_actions),
        )

        try:
            loaded = int(request.POST.get("_inline_controls_loaded") or 0)
        except ValueError:
            loaded = 0
        # The current filters come from the query string, as for the page.
        formset = formset_class(
            instance=obj,
            prefix=prefix,
            queryset=inline.get_queryset(request),
        )
        formset.get_queryset()
        queryset = formset.inline_controls.filtered_queryset
        action = inline.get_inline_bulk_actions(request, obj).get(
            request.POST.get("action", "")
        )
        if action is None:
            return HttpResponseBadRequest("Unknown or forbidden action.")
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
