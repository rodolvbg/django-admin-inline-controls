"""Pages of rows: links, or more loaded on scroll."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django_admin_inline_controls.controls import PAGES

from .base import InlineControlsBaseMixin

if TYPE_CHECKING:
    from django.http import HttpRequest


class InlinePaginationMixin(InlineControlsBaseMixin):
    """``inline_per_page`` rows a page, as page links or loaded on scroll."""

    #: Rows per page. ``None`` disables pagination.
    inline_per_page: int | None = None
    #: ``"pages"`` renders page links, ``"infinite"`` loads more on scroll.
    inline_pagination: str = PAGES

    def get_inline_per_page(self, request: HttpRequest, obj: Any) -> int | None:
        return self.inline_per_page
