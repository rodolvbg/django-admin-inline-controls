"""Row actions: buttons on each saved row of an inline.

An action is a method of the inline (or a callable) in one of two forms:

- for one row, ``action(inline, request, obj, parent_obj=None)`` — the
  signature of django-inline-actions, so its actions can be reused as they
  are;
- for a queryset, ``action(inline, request, queryset)`` — an inline action
  (``@inline_action``), run on a queryset with only that row.

Both return ``None`` to re-render the inline with the messages sent through
``inline.message_user()``, or an ``HttpResponse`` (a file download or a
redirect). Per-row label, CSS classes and HTML attributes come from the
action's ``short_description`` / ``css_classes`` / ``attribute_properties``
or from ``get_<action>_label(obj)`` / ``get_<action>_css(obj)`` /
``get_<action>_attr(obj)`` on the inline, as in django-inline-actions.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from django.contrib import messages
from django.contrib.admin.utils import model_format_dict, quote
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html_join
from django.utils.safestring import SafeString, mark_safe
from django.utils.text import capfirst
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from django_admin_inline_controls.actions import delete_selected, inline_action

#: The request and parent object an inline is rendered for, by inline: the
#: row actions' column only gets the row. A context variable, not an
#: attribute, since admin instances are shared between requests.
RENDER_CONTEXT: ContextVar[dict[int, tuple[HttpRequest, Any]] | None] = ContextVar(
    "inline_controls_render_context", default=None
)


def set_render_context(inline: Any, request: HttpRequest, parent: Any) -> None:
    context = dict(RENDER_CONTEXT.get() or {})
    context[id(inline)] = (request, parent)
    RENDER_CONTEXT.set(context)


def get_render_context(inline: Any) -> tuple[HttpRequest | None, Any]:
    return (RENDER_CONTEXT.get() or {}).get(id(inline), (None, None))


@inline_action(
    permissions=["delete"],
    description=_("Delete"),
    confirmation=_("Delete “%(object)s”? This cannot be undone."),
)
def delete(inline: Any, request: HttpRequest, queryset: Any) -> None:
    """Delete the row (``delete()`` overrides and signals run), recorded in
    the parent's history, like ``delete_selected``."""
    return delete_selected(inline, request, queryset)


@inline_action(permissions=["view"], description=_("View"))
def view(inline: Any, request: HttpRequest, obj: Any, parent_obj: Any = None) -> Any:
    """Open the row's change view (its own ``ModelAdmin``)."""
    url = change_url(inline, obj)
    if url is None:  # pragma: no cover - only offered when it has one
        inline.message_user(request, gettext("This item has no page."), messages.ERROR)
        return None
    return HttpResponseRedirect(url)


#: Row actions that can be referenced by name in ``inline_row_actions``.
BUILTIN_ROW_ACTIONS: dict[str, Callable[..., Any]] = {"delete": delete, "view": view}


def change_url(inline: Any, obj: Any) -> str | None:
    """The change view of ``obj`` in the inline's admin site, if registered."""
    opts = obj._meta
    try:
        return reverse(
            f"{inline.admin_site.name}:{opts.app_label}_{opts.model_name}_change",
            args=[quote(obj.pk)],
        )
    except NoReverseMatch:
        return None


def takes_one_row(function: Callable[..., Any]) -> bool:
    """Whether ``function`` acts on one row (``obj``) rather than a queryset."""
    try:
        return "obj" in inspect.signature(function).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins, C functions
        return False


@dataclass(frozen=True)
class RowActionSpec:
    """A row action as offered for one row."""

    name: str
    function: Callable[..., Any]
    label: str
    css_classes: str
    #: Extra HTML attributes of the button.
    attrs: SafeString
    confirmation: str | None
    #: A link instead of a button (``view``).
    url: str | None = None


def row_action_spec(
    inline: Any, name: str, function: Callable[..., Any], obj: Any
) -> RowActionSpec:
    """``function`` as ``name``'s action for the row ``obj``."""
    names = {**model_format_dict(inline.model._meta), "object": obj, "count": 1}

    def hook(kind: str) -> Any:
        method = getattr(inline, f"get_{name}_{kind}", None)
        return method(obj=obj) if callable(method) else None

    label = hook("label")
    if label is None:
        label = getattr(function, "short_description", None)
        label = (
            str(label) % names
            if label is not None
            else capfirst(name.replace("_", " "))
        )
    css = hook("css")
    if css is None:
        css = getattr(function, "css_classes", "")
    attrs = hook("attr")
    if attrs is None:
        attrs = getattr(function, "attribute_properties", "")
    if isinstance(attrs, dict):
        attrs = format_html_join(" ", '{}="{}"', attrs.items())
    else:
        # A string is used as it is, as in django-inline-actions.
        attrs = mark_safe(attrs)  # noqa: S308
    confirmation = getattr(function, "confirmation", None)
    return RowActionSpec(
        name=name,
        function=function,
        label=str(label),
        css_classes=str(css),
        attrs=attrs,
        confirmation=None if confirmation is None else str(confirmation) % names,
        url=change_url(inline, obj) if function is view else None,
    )


def run_row_action(
    inline: Any, request: HttpRequest, action: RowActionSpec, obj: Any, parent: Any
) -> Any:
    """Call the action on the row ``obj`` in the form it was written for."""
    function = action.function
    if takes_one_row(function):
        return function(inline, request, obj, parent_obj=parent)
    queryset = type(obj)._default_manager.filter(pk=obj.pk)
    return function(inline, request, queryset)


__all__ = [
    "BUILTIN_ROW_ACTIONS",
    "RowActionSpec",
    "delete",
    "view",
]
