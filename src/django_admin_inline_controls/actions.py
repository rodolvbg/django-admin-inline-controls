"""Inline actions: like the changelist's, for the rows of one inline.

An action is called as ``action(inline, request, queryset)``, where
``queryset`` holds the selected rows (always children of the parent object
being edited) and ``request.inline_controls_parent`` is that parent. Return
``None`` to re-render the inline with the messages sent through
``inline.message_user()``, or an ``HttpResponse`` (a file download or a
redirect).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from django.contrib import admin, messages
from django.db import router, transaction
from django.db.models import ProtectedError, QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

if TYPE_CHECKING:
    from django.utils.functional import _StrOrPromise as StrOrPromise

InlineAction = Callable[[Any, HttpRequest, QuerySet], Any]


def inline_action(
    function: InlineAction | None = None,
    *,
    permissions: Sequence[str] | None = None,
    description: StrOrPromise | None = None,
    confirmation: StrOrPromise | None = None,
) -> Any:
    """``@admin.action`` plus an optional confirmation prompt::

        @inline_action(
            description="Mark selected %(verbose_name_plural)s as published",
            confirmation="Publish the selected %(verbose_name_plural)s?",
        )
        def publish(inline, request, queryset):
            queryset.update(status="published")

    ``description`` and ``confirmation`` may use ``%(verbose_name)s`` and
    ``%(verbose_name_plural)s``; ``confirmation`` also ``%(count)s``, the
    number of rows the action will run on. Plain ``@admin.action`` functions
    work too.
    """

    def decorator(func: InlineAction) -> InlineAction:
        func = admin.action(permissions=permissions, description=description)(func)
        if confirmation is not None:
            func.confirmation = confirmation  # type: ignore[attr-defined]
        return func

    return decorator if function is None else decorator(function)


@inline_action(
    permissions=["delete"],
    description=_("Delete selected %(verbose_name_plural)s"),
    confirmation=_(
        "Delete %(count)s selected %(verbose_name_plural)s? This cannot be undone."
    ),
)
def delete_selected(inline: Any, request: HttpRequest, queryset: QuerySet) -> None:
    """Delete the selected rows one by one (so ``delete()`` overrides and
    signals run, as when they're deleted from the change form) and record
    it in the parent's history."""
    objects = list(queryset)
    opts = queryset.model._meta
    parent = getattr(request, "inline_controls_parent", None)
    try:
        with transaction.atomic(using=router.db_for_write(queryset.model)):
            for obj in objects:
                obj.delete()
    except ProtectedError as error:
        inline.message_user(
            request,
            _("Cannot delete: %(objects)s are referenced by protected objects.")
            % {"objects": ", ".join(str(obj) for obj in error.protected_objects)},
            messages.ERROR,
        )
        return None
    parent_admin = parent and inline.admin_site._registry.get(type(parent))
    if parent_admin is not None and objects:
        parent_admin.log_change(
            request,
            parent,
            [
                {"deleted": {"name": str(opts.verbose_name), "object": str(obj)}}
                for obj in objects
            ],
        )
    inline.message_user(
        request,
        ngettext(
            "Deleted %(count)d %(name)s.",
            "Deleted %(count)d %(name)s.",
            len(objects),
        )
        % {
            "count": len(objects),
            "name": opts.verbose_name
            if len(objects) == 1
            else opts.verbose_name_plural,
        },
        messages.SUCCESS,
    )
    return None


#: Actions that can be referenced by name in ``inline_actions``.
BUILTIN_ACTIONS: dict[str, InlineAction] = {"delete_selected": delete_selected}

__all__ = ["BUILTIN_ACTIONS", "delete_selected", "inline_action"]
