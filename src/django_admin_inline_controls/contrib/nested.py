"""django-nested-admin integration. Requires the ``nested`` extra."""

from __future__ import annotations

from typing import Any

try:
    import nested_admin  # noqa: F401
except ImportError as e:
    raise ImportError(
        "django_admin_inline_controls.contrib.nested requires django-nested-admin. "
        "Install it with: pip install django-admin-inline-controls[nested]"
    ) from e

from django.core import checks

from django_admin_inline_controls.controls import INFINITE
from django_admin_inline_controls.mixins import InlineControlsMixin


class NestedInlineControlsMixin(InlineControlsMixin):
    """``InlineControlsMixin`` for ``nested_admin`` inlines::

        class BookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
            model = Book
            inline_per_page = 20

    nested_admin keeps its own client-side formset state, so filters,
    sorting and page links reload the page instead of swapping the inline,
    and infinite scroll, the save-inline button and inline actions are not
    available.
    """

    inline_controls_ajax = False

    def check(self, **kwargs: Any) -> list[Any]:
        errors = super().check(**kwargs)
        if self.inline_pagination == INFINITE:
            errors.append(
                checks.Error(
                    f"'{type(self).__qualname__}.inline_pagination' cannot be "
                    f"'{INFINITE}' on a nested_admin inline.",
                    obj=type(self),
                    id="admin_inline_controls.E101",
                )
            )
        if self.inline_save_button:
            errors.append(
                checks.Error(
                    f"'{type(self).__qualname__}.inline_save_button' is not "
                    "supported on a nested_admin inline.",
                    obj=type(self),
                    id="admin_inline_controls.E102",
                )
            )
        if self.inline_actions:
            errors.append(
                checks.Error(
                    f"'{type(self).__qualname__}.inline_actions' is not "
                    "supported on a nested_admin inline.",
                    obj=type(self),
                    id="admin_inline_controls.E103",
                )
            )
        if self.inline_row_actions:
            errors.append(
                checks.Error(
                    f"'{type(self).__qualname__}.inline_row_actions' is not "
                    "supported on a nested_admin inline.",
                    obj=type(self),
                    id="admin_inline_controls.E105",
                )
            )
        return errors


__all__ = ["NestedInlineControlsMixin"]
