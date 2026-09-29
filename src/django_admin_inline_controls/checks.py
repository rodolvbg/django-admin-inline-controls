"""System checks for ``InlineControlsMixin`` options."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from django.core import checks
from django.core.exceptions import FieldDoesNotExist

from django_admin_inline_controls.controls import INFINITE, PAGES

if TYPE_CHECKING:
    from django_admin_inline_controls.mixins import InlineControlsMixin


def check_inline_controls(inline: InlineControlsMixin) -> list[checks.CheckMessage]:
    from django_admin_inline_controls.mixins import (
        InlineControlsAdminMixin,
        resolve_lookup,
    )

    errors: list[checks.CheckMessage] = []
    name = type(inline).__qualname__

    def error(msg: str, id: str) -> None:
        errors.append(checks.Error(msg, obj=type(inline), id=id))

    if inline.inline_pagination not in (PAGES, INFINITE):
        error(
            f"The value of '{name}.inline_pagination' must be '{PAGES}' or "
            f"'{INFINITE}'.",
            "admin_inline_controls.E001",
        )

    per_page: Any = inline.inline_per_page
    if per_page is not None and (
        not isinstance(per_page, int) or isinstance(per_page, bool) or per_page < 1
    ):
        error(
            f"The value of '{name}.inline_per_page' must be a positive integer "
            "or None.",
            "admin_inline_controls.E002",
        )

    if inline.inline_pagination == INFINITE and per_page is None:
        error(
            f"'{name}.inline_pagination = \"{INFINITE}\"' requires 'inline_per_page'.",
            "admin_inline_controls.E003",
        )

    if isinstance(inline.inline_filter_fields, str):
        error(
            f"The value of '{name}.inline_filter_fields' must be a list or tuple.",
            "admin_inline_controls.E004",
        )
    else:
        for lookup in inline.inline_filter_fields:
            try:
                resolve_lookup(inline.model, lookup)
            except FieldDoesNotExist:
                error(
                    f"'{name}.inline_filter_fields' refers to '{lookup}', which "
                    f"is not a field of '{inline.model._meta.label}'.",
                    "admin_inline_controls.E005",
                )

    ordering_fields: Any = inline.inline_ordering_fields
    if isinstance(ordering_fields, str) or not isinstance(
        ordering_fields, list | tuple | Mapping
    ):
        error(
            f"The value of '{name}.inline_ordering_fields' must be a list, tuple "
            "or dict.",
            "admin_inline_controls.E006",
        )
    else:
        for column in ordering_fields:
            if not isinstance(column, str) or column.startswith("-") or "," in column:
                error(
                    f"'{name}.inline_ordering_fields' contains {column!r}; column "
                    "names must be strings without a leading '-' or commas.",
                    "admin_inline_controls.E007",
                )

    if inline.inline_save_button:
        parent_admin = inline.admin_site._registry.get(inline.parent_model)
        if parent_admin is not None and not isinstance(
            parent_admin, InlineControlsAdminMixin
        ):
            error(
                f"'{name}.inline_save_button' requires "
                f"'{type(parent_admin).__qualname__}' to inherit from "
                "'InlineControlsAdminMixin'.",
                "admin_inline_controls.E008",
            )

    return errors
