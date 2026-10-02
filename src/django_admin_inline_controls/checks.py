"""System checks for ``InlineControlsMixin`` options."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from django.contrib.admin.utils import label_for_field
from django.core import checks
from django.core.exceptions import FieldDoesNotExist

from django_admin_inline_controls.controls import (
    DEFAULT_SELECTORS,
    FOOTER_FILTERED,
    FOOTER_PAGE,
    INFINITE,
    PAGES,
)

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

    footer_rows: Any = inline.inline_footer_rows
    if isinstance(footer_rows, str) or not isinstance(footer_rows, list | tuple):
        error(
            f"The value of '{name}.inline_footer_rows' must be a list of "
            "(label, {column: value}) pairs.",
            "admin_inline_controls.E013",
        )
    else:
        for index, row in enumerate(footer_rows):
            if not (
                isinstance(row, list | tuple)
                and len(row) == 2
                and isinstance(row[1], Mapping)
            ):
                error(
                    f"'{name}.inline_footer_rows[{index}]' must be a "
                    "(label, {column: value}) pair.",
                    "admin_inline_controls.E013",
                )
                continue
            for column in row[1]:
                try:
                    label_for_field(column, inline.model, inline)  # type: ignore[call-overload]
                except AttributeError:
                    error(
                        f"'{name}.inline_footer_rows[{index}]' refers to "
                        f"'{column}', which is not a field of "
                        f"'{inline.model._meta.label}' or of the inline.",
                        "admin_inline_controls.E014",
                    )

    if not isinstance(inline.inline_footer_tfoot, bool):
        error(
            f"The value of '{name}.inline_footer_tfoot' must be True or False.",
            "admin_inline_controls.E017",
        )

    if inline.inline_footer_scope not in (FOOTER_FILTERED, FOOTER_PAGE):
        error(
            f"The value of '{name}.inline_footer_scope' must be "
            f"'{FOOTER_FILTERED}' or '{FOOTER_PAGE}'.",
            "admin_inline_controls.E015",
        )
    elif inline.inline_footer_scope == FOOTER_PAGE and (
        inline.inline_pagination == INFINITE
    ):
        error(
            f"'{name}.inline_footer_scope = \"{FOOTER_PAGE}\"' can't be used with "
            "infinite scroll (the shown rows change as more are loaded).",
            "admin_inline_controls.E016",
        )

    selectors: Any = inline.inline_controls_selectors
    if not isinstance(selectors, Mapping):
        error(
            f"The value of '{name}.inline_controls_selectors' must be a dict.",
            "admin_inline_controls.E011",
        )
    else:
        for key, value in selectors.items():
            values = [value] if isinstance(value, str) else value
            if key not in DEFAULT_SELECTORS or not (
                isinstance(values, list | tuple)
                and values
                and all(isinstance(v, str) and v for v in values)
            ):
                error(
                    f"'{name}.inline_controls_selectors' has an invalid entry "
                    f"{key!r}: keys must be one of {sorted(DEFAULT_SELECTORS)} "
                    "and values a selector or a non-empty list of selectors.",
                    "admin_inline_controls.E012",
                )

    parent_admin = inline.admin_site._registry.get(inline.parent_model)
    missing_admin_mixin = parent_admin is not None and not isinstance(
        parent_admin, InlineControlsAdminMixin
    )
    for option, error_id in (
        ("inline_save_button", "admin_inline_controls.E008"),
        ("inline_actions", "admin_inline_controls.E010"),
        ("inline_row_actions", "admin_inline_controls.E019"),
    ):
        if getattr(inline, option) and missing_admin_mixin:
            error(
                f"'{name}.{option}' requires "
                f"'{type(parent_admin).__qualname__}' to inherit from "
                "'InlineControlsAdminMixin'.",
                error_id,
            )

    for action in inline.inline_actions:
        try:
            _, func = inline._resolve_inline_action(action)
        except AttributeError:
            func = None
        if not callable(func):
            error(
                f"'{name}.inline_actions' contains {action!r}, which is not a "
                f"method of '{name}', a callable, or a built-in action.",
                "admin_inline_controls.E009",
            )

    for action in inline.inline_row_actions:
        try:
            _, func = inline._resolve_inline_row_action(action)
        except AttributeError:
            func = None
        if not callable(func):
            error(
                f"'{name}.inline_row_actions' contains {action!r}, which is not "
                f"a method of '{name}', a callable, or a built-in row action "
                "('view', 'delete').",
                "admin_inline_controls.E018",
            )

    return errors
