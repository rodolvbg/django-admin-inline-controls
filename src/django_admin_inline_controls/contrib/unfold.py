"""django-unfold integration."""

from __future__ import annotations

from typing import Any

try:
    import unfold  # noqa: F401
except ImportError as e:
    raise ImportError(
        "django_admin_inline_controls.contrib.unfold requires django-unfold. "
        "Install it with: pip install django-admin-inline-controls[unfold]"
    ) from e

from django import forms
from django.core import checks
from django.http import HttpRequest

from django_admin_inline_controls.mixins import InlineControlsMixin

#: Where the controls go in Unfold's inline templates; applied under the
#: inline's own ``inline_controls_selectors``.
UNFOLD_SELECTORS: dict[str, list[str]] = {
    "container": [
        "[data-inline-type] > fieldset",
        "[data-inline-type] > .inline-related > fieldset",
    ],
    "table_head": ["table thead"],
    # Each form is a <tbody> (tabular) or a <div> (stacked), without an id.
    "form_rows": ['[id="{prefix}-data"] > .form-group'],
    "saved_row": [".original"],
    "row_label": [
        ':scope > tr > td > p[class~="group/title"]',
        ":scope > .form-row > h3 > span",
        ":scope > tr.form-row > td",
    ],
}


class UnfoldInlineControlsMixin(InlineControlsMixin):
    """``InlineControlsMixin`` for Unfold's inlines::

        from unfold.admin import TabularInline

        class BookInline(UnfoldInlineControlsMixin, TabularInline):
            model = Book
            inline_per_page = 20

    Places the controls in Unfold's markup, styles them with its colors
    (light and dark) and re-binds its "Add another" / delete buttons after an
    inline is refreshed. Paginate with ``inline_per_page``, not Unfold's
    ``per_page``.
    """

    def get_inline_controls_selectors(
        self, request: HttpRequest, obj: Any
    ) -> dict[str, list[str]]:
        selectors = super().get_inline_controls_selectors(request, obj)
        for key, value in UNFOLD_SELECTORS.items():
            if key not in self.inline_controls_selectors:
                selectors[key] = list(value)
        return selectors

    @property
    def media(self) -> forms.Media:
        return super().media + forms.Media(
            js=["django_admin_inline_controls/js/contrib/unfold.js"],
            css={"all": ["django_admin_inline_controls/css/contrib/unfold.css"]},
        )

    def check(self, **kwargs: Any) -> list[Any]:
        errors = super().check(**kwargs)
        if getattr(self, "per_page", None):
            errors.append(
                checks.Error(
                    f"'{type(self).__qualname__}.per_page' paginates the inline "
                    "a second time; use 'inline_per_page' instead.",
                    obj=type(self),
                    id="admin_inline_controls.E104",
                )
            )
        return errors


__all__ = ["UNFOLD_SELECTORS", "UnfoldInlineControlsMixin"]
