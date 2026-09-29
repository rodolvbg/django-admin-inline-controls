"""Per-request state of a controlled inline formset.

``InlineControls`` reads this inline's query parameters (namespaced by the
formset prefix so several inlines on one page never clash), then filters,
orders and paginates the formset queryset and exposes everything the
templates and the JS need.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.contrib.admin.utils import label_for_field, quote
from django.core.exceptions import ValidationError
from django.core.paginator import Page, Paginator
from django.db.models import QuerySet
from django.db.models.expressions import OrderBy
from django.forms import Form
from django.http import HttpRequest, QueryDict
from django.urls import NoReverseMatch, reverse
from django.utils.functional import cached_property
from django.utils.text import capfirst
from django.utils.translation import gettext

from django_admin_inline_controls.types import Ordering, OrderingFields, OrderingValue

if TYPE_CHECKING:
    from django_admin_inline_controls.mixins import InlineControlsMixin

PAGES = "pages"
INFINITE = "infinite"


@dataclass(frozen=True)
class OrderingColumn:
    """A sortable column as rendered in the inline header or toolbar."""

    name: str
    label: str
    direction: str  # "ascending", "descending" or ""
    priority: int  # 1-based position in the current ordering, 0 if unsorted
    toggle_url: str
    remove_url: str

    def as_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "direction": self.direction,
            "priority": self.priority,
            "toggleUrl": self.toggle_url,
            "removeUrl": self.remove_url,
        }


@dataclass(frozen=True)
class PageLink:
    number: int | str
    url: str | None
    current: bool = False


def normalize_ordering_fields(
    ordering_fields: OrderingFields,
) -> dict[str, OrderingValue]:
    """Return ``{column: expression}`` from a sequence or mapping."""
    if isinstance(ordering_fields, Mapping):
        return dict(ordering_fields)
    return {name: name for name in ordering_fields}


def ordering_expression(value: OrderingValue, descending: bool) -> Any:
    """Build the ``order_by()`` argument for a column in one direction.

    ``value`` may be a field path (``"author__name"``), an expression
    (``Lower("name")``, ``F("date").asc(nulls_last=True)``) or an explicit
    ``(ascending, descending)`` pair for full control over both directions.
    """
    if isinstance(value, tuple):
        return value[1] if descending else value[0]
    if isinstance(value, str):
        path = value.removeprefix("-")
        flipped = value.startswith("-") != descending
        return f"-{path}" if flipped else path
    if isinstance(value, OrderBy):
        if not descending:
            return value
        reversed_value = value.copy()
        reversed_value.reverse_ordering()
        return reversed_value
    return value.desc() if descending else value.asc()


class InlineControls:
    """Filtering, ordering and pagination state for one inline formset."""

    def __init__(
        self,
        inline: InlineControlsMixin,
        request: HttpRequest,
        parent: Any,
        prefix: str,
        pages_loaded: int | None = None,
    ) -> None:
        self.inline = inline
        self.request = request
        self.parent = parent
        self.prefix = prefix
        self.params: QueryDict = request.GET
        self.mode = inline.inline_pagination
        self.per_page = inline.get_inline_per_page(request, parent)
        self.ordering_fields = normalize_ordering_fields(
            inline.get_inline_ordering_fields(request, parent)
        )
        self.ordering = self._parse_ordering()
        self.filter_form: Form | None = None
        self.paginator: Paginator | None = None
        self.page: Page | None = None
        self.loaded_count: int | None = None
        self.pages_loaded = pages_loaded

    # Query parameter names -------------------------------------------------

    @property
    def page_param(self) -> str:
        return f"{self.prefix}-page"

    @property
    def ordering_param(self) -> str:
        return f"{self.prefix}-o"

    @property
    def filter_prefix(self) -> str:
        return f"{self.prefix}-f"

    @property
    def filter_form_id(self) -> str:
        """Id of a form element that is never rendered.

        Filter widgets point their ``form`` attribute at it, which detaches
        them from the admin change form: they are not submitted on save and
        pressing Enter in them does not save the object.
        """
        return f"{self.prefix}-inline-controls-filters"

    @property
    def container_id(self) -> str:
        return f"{self.prefix}-inline-controls"

    # Queryset --------------------------------------------------------------

    def apply(self, queryset: QuerySet, bound_pks: list[Any] | None) -> QuerySet:
        """Filter, order and paginate ``queryset``.

        On a bound (POST) formset the submitted rows may come from several
        pages (infinite scroll), so instead of slicing the current page the
        queryset is restricted to the submitted primary keys.
        """
        self.filter_form, queryset = self.inline.get_inline_filtered_queryset(
            self.request, self.parent, queryset, self.params, self.filter_prefix
        )
        if self.filter_form is not None:
            for field in self.filter_form.fields.values():
                field.widget.attrs["form"] = self.filter_form_id

        queryset = queryset.order_by(*self._order_by(queryset))
        #: Filtered and ordered, before pagination: what actions run on
        #: when "select all" is used.
        self.filtered_queryset = queryset

        if self.per_page:
            self.paginator = Paginator(queryset, self.per_page)
            self.page = self.paginator.get_page(self.params.get(self.page_param))

        if bound_pks is not None:
            if self.mode == INFINITE:
                self.loaded_count = len(bound_pks)
            return queryset.filter(pk__in=bound_pks)
        if self.page is not None and self.page.paginator.count:
            self.loaded_count = self.page.end_index()
            start = self.page.start_index() - 1
            if self.mode == INFINITE and self.pages_loaded and self.per_page:
                start = 0
                self.loaded_count = min(
                    self.page.paginator.count, self.pages_loaded * self.per_page
                )
            page_pks = queryset.values_list("pk", flat=True)[start : self.loaded_count]
            return queryset.filter(pk__in=list(page_pks))
        return queryset

    def _order_by(self, queryset: QuerySet) -> list[Any]:
        order_by = [
            ordering_expression(self.ordering_fields[name], descending)
            for name, descending in self.ordering
        ]
        default = list(
            self.inline.inline_default_ordering
            or queryset.query.order_by
            or queryset.model._meta.ordering
        )
        order_by.extend(default)
        # Pagination needs a total order or rows can repeat across pages.
        pk_name = queryset.model._meta.pk.name
        pk_values = {"pk", "-pk", pk_name, f"-{pk_name}"}
        if not any(value in pk_values for value in order_by):
            order_by.append("pk")
        return order_by

    # Ordering --------------------------------------------------------------

    def _parse_ordering(self) -> Ordering:
        """Parse ``?<prefix>-o=name,-date`` keeping only declared columns.

        Unknown names are dropped: ordering by an arbitrary field would let
        anyone infer the values of fields the inline never shows.
        """
        ordering: Ordering = []
        seen: set[str] = set()
        for token in self.params.get(self.ordering_param, "").split(","):
            name = token.strip().removeprefix("-")
            if name in self.ordering_fields and name not in seen:
                seen.add(name)
                ordering.append((name, token.strip().startswith("-")))
        return ordering

    def _encode_ordering(self, ordering: Ordering) -> str:
        return ",".join(f"-{name}" if desc else name for name, desc in ordering)

    @property
    def ordering_columns(self) -> list[OrderingColumn]:
        columns = []
        current = dict(self.ordering)
        positions = {name: index for index, (name, _) in enumerate(self.ordering)}
        for name in self.ordering_fields:
            others = [item for item in self.ordering if item[0] != name]
            if name in current:
                descending = current[name]
                toggled = list(self.ordering)
                toggled[positions[name]] = (name, not descending)
                direction = "descending" if descending else "ascending"
                priority = positions[name] + 1
            else:
                # Like the changelist: a newly sorted column becomes primary.
                toggled = [(name, False), *others]
                direction = ""
                priority = 0
            columns.append(
                OrderingColumn(
                    name=name,
                    label=self._column_label(name),
                    direction=direction,
                    priority=priority,
                    toggle_url=self._url(
                        {self.ordering_param: self._encode_ordering(toggled)},
                        reset_page=True,
                    ),
                    remove_url=self._url(
                        {self.ordering_param: self._encode_ordering(others)},
                        reset_page=True,
                    ),
                )
            )
        return columns

    def _column_label(self, name: str) -> str:
        try:
            label = label_for_field(name, self.inline.model, self.inline)  # type: ignore[call-overload]
            return str(capfirst(label))
        except AttributeError:
            return name

    # Pagination ------------------------------------------------------------

    @property
    def is_paginated(self) -> bool:
        return self.paginator is not None and self.paginator.num_pages > 1

    @property
    def total_count(self) -> int | None:
        return None if self.paginator is None else self.paginator.count

    @property
    def page_links(self) -> list[PageLink]:
        if self.page is None or self.paginator is None:
            return []
        links = []
        for number in self.paginator.get_elided_page_range(
            self.page.number, on_each_side=2, on_ends=1
        ):
            if number == self.paginator.ELLIPSIS:
                links.append(PageLink(number=number, url=None))
            else:
                links.append(
                    PageLink(
                        number=number,
                        url=self._url({self.page_param: str(number)}),
                        current=number == self.page.number,
                    )
                )
        return links

    @property
    def next_page_url(self) -> str | None:
        """URL of the next page to append in infinite mode."""
        if self.page is None or self.paginator is None or not self.per_page:
            return None
        loaded_pages = -(-(self.loaded_count or 0) // self.per_page)
        if loaded_pages >= self.paginator.num_pages:
            return None
        return self._url({self.page_param: str(loaded_pages + 1)})

    # Filters ---------------------------------------------------------------

    @property
    def filter_param_names(self) -> list[str]:
        if self.filter_form is None:
            return []
        return [self.filter_form.add_prefix(name) for name in self.filter_form.fields]

    @property
    def is_filtered(self) -> bool:
        return any(self.params.get(name) for name in self.filter_param_names)

    # Saving ----------------------------------------------------------------

    def _endpoint(self, kind: str) -> str | None:
        """URL of an ``InlineControlsAdminMixin`` endpoint, if routed."""
        opts = self.inline.parent_model._meta
        name = f"{opts.app_label}_{opts.model_name}_inline_controls_{kind}"
        try:
            return reverse(
                f"{self.inline.admin_site.name}:{name}",
                args=[quote(self.parent.pk), self.prefix],
            )
        except NoReverseMatch:
            return None

    @cached_property
    def save_url(self) -> str | None:
        """Endpoint that saves only this inline, if enabled and routed."""
        return self._endpoint("save") if self.inline.inline_save_button else None

    # Actions ---------------------------------------------------------------

    @cached_property
    def actions(self) -> list[Any]:
        if not self.inline.inline_actions or self._endpoint("action") is None:
            return []
        return list(self.inline.get_inline_actions(self.request, self.parent).values())

    @property
    def action_url(self) -> str | None:
        return self._endpoint("action") if self.actions else None

    @property
    def actions_form_id(self) -> str:
        """Detached form id for the action select and row checkboxes."""
        return f"{self.prefix}-inline-controls-actions"

    @property
    def save_label(self) -> str:
        return gettext("Save %(name)s") % {
            "name": self.inline.model._meta.verbose_name_plural
        }

    @property
    def has_toolbar(self) -> bool:
        return bool(self.filter_form or self.ordering_columns or self.actions)

    @property
    def has_footer(self) -> bool:
        return self.paginator is not None or self.save_url is not None

    # URLs and config -------------------------------------------------------

    def _url(self, changes: Mapping[str, str], reset_page: bool = False) -> str:
        params = self.params.copy()
        if reset_page:
            params.pop(self.page_param, None)
        for key, value in changes.items():
            if value:
                params[key] = value
            else:
                params.pop(key, None)
        query = params.urlencode()
        return f"?{query}" if query else "?"

    @property
    def config_json(self) -> str:
        return json.dumps(
            {
                "prefix": self.prefix,
                "mode": self.mode if self.per_page else None,
                "ajax": self.inline.inline_controls_ajax,
                "pageParam": self.page_param,
                "filterPrefix": self.filter_prefix,
                "filterFormId": self.filter_form_id,
                "filterParams": self.filter_param_names,
                "ordering": [column.as_json() for column in self.ordering_columns],
                "nextUrl": self.next_page_url if self.mode == INFINITE else None,
                "saveUrl": self.save_url,
                "actionUrl": self.action_url,
                "actionsFormId": self.actions_form_id,
                "actions": [
                    {
                        "name": action.name,
                        "confirmation": action.confirmation,
                    }
                    for action in self.actions
                ],
                "pkName": self.inline.model._meta.pk.name,
                "loadedCount": self.loaded_count,
                "totalCount": self.total_count,
                "messages": {
                    "unsaved": gettext(
                        "You have unsaved changes in this inline that will be "
                        "lost. Continue?"
                    ),
                    "sortRemove": gettext("Remove from sorting"),
                    "sortToggle": gettext("Toggle sorting"),
                    "saveFailed": gettext(
                        "The changes could not be saved. Please try again."
                    ),
                    "actionFailed": gettext(
                        "The action could not be run. Please try again."
                    ),
                    "noAction": gettext("No action selected."),
                    "noSelection": gettext(
                        "Items must be selected in order to perform actions on "
                        "them. No items have been changed."
                    ),
                    "selected": gettext("%(sel)s of %(cnt)s selected"),
                    "selectAll": gettext("Select all %(total)s"),
                    "allSelected": gettext("All %(total)s selected"),
                    "selectRow": gettext("Select this row"),
                    "selectAllRows": gettext("Select all rows on this page"),
                },
            }
        )


def bound_primary_keys(formset: Any) -> list[Any]:
    """Primary keys submitted by a bound model formset, invalid ones dropped."""
    pk_field = formset.model._meta.pk
    pks = []
    for index in range(formset.initial_form_count()):
        raw = formset.data.get(f"{formset.add_prefix(index)}-{pk_field.name}")
        if raw in (None, ""):
            continue
        try:
            pks.append(pk_field.to_python(raw))
        except ValidationError:
            continue
    return pks
