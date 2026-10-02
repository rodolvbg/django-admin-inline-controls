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


#: Actions that can be referenced by name in ``inline_bulk_actions``.
BUILTIN_BULK_ACTIONS: dict[str, InlineAction] = {"delete_selected": delete_selected}


# Row actions as django-inline-actions' mixins ---------------------------------


class ViewAction:
    """A "View" link on each row, to its change view::

    class BookInline(ViewAction, InlineControlsMixin, admin.TabularInline):
        ...
    """

    inline_actions: list[str | InlineAction] | None = ["view_action"]

    @inline_action(permissions=["view"], description=_("View"))
    def view_action(
        self, request: HttpRequest, obj: Any, parent_obj: Any = None
    ) -> Any:
        from django_admin_inline_controls.row_actions import view

        return view(self, request, obj, parent_obj)

    view_action.inline_actions_link = True


class DeleteAction:
    """A "Delete" button on each row (with the delete permission)::

    class BookInline(DeleteAction, InlineControlsMixin, admin.TabularInline):
        ...
    """

    def get_inline_actions(self, request: HttpRequest | None, obj: Any = None) -> Any:
        actions = list(super().get_inline_actions(request, obj))  # type: ignore[misc]
        if "delete_action" not in actions:
            actions.append("delete_action")
        return actions

    @inline_action(
        permissions=["delete"],
        description=_("Delete"),
        confirmation=_("Delete “%(object)s”? This cannot be undone."),
    )
    def delete_action(self, request: HttpRequest, queryset: QuerySet) -> None:
        return delete_selected(self, request, queryset)


class DefaultActionsMixin(ViewAction, DeleteAction):
    """``ViewAction`` and ``DeleteAction``."""

    inline_actions: list[str | InlineAction] | None = []


__all__ = [
    "BUILTIN_BULK_ACTIONS",
    "DefaultActionsMixin",
    "DeleteAction",
    "ViewAction",
    "delete_selected",
    "inline_action",
]
