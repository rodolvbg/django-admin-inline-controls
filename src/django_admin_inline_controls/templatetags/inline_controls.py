"""Server-side rendering of the footer rows inside the inline's own table."""

from __future__ import annotations

import re
from typing import Any

from django import template
from django.utils.safestring import SafeString, mark_safe

register = template.Library()


def _visible_columns(inline_admin_formset: Any) -> list[str]:
    """Names of the table's columns after "original", in order: the fields
    Django's tabular template shows (hidden widgets have no visible column)."""
    columns = []
    for field in inline_admin_formset.fields():
        widget = field["widget"]
        hidden = (
            widget.get("is_hidden") if isinstance(widget, dict) else widget.is_hidden
        )
        if not hidden:
            columns.append(field["name"])
    return columns


def _header_width(html: str) -> int:
    """Columns of the table's header row, as rendered (it varies with the
    Django version, the theme and the delete permission)."""
    head = re.search(r"<thead.*?</thead>", html, re.S)
    if not head:
        return 0
    total = 0
    for attrs in re.findall(r"<th\b([^>]*)>", head.group()):
        span = re.search(r'colspan="(\d+)"', attrs)
        total += int(span.group(1)) if span else 1
    return total


@register.simple_tag(takes_context=True)
def inline_controls_render_inline(
    context: template.Context, template_name: str
) -> SafeString:
    """Render the inline's template (Django's, a theme's or your own) and, if
    it has a table, insert the footer rows as its <tfoot> — no JS, and no
    copy of Django's template to keep in sync."""
    engine = context.template.engine  # type: ignore[union-attr]
    html = engine.get_template(template_name).render(context)
    controls = context.get("controls")
    formset = context["inline_admin_formset"]
    if not controls or not controls.footer_rows or not formset.opts.inline_footer_tfoot:
        return mark_safe(html)
    position = html.rfind("</table>")
    rows = (
        controls.tfoot_rows(_visible_columns(formset), _header_width(html))
        if position != -1
        else None
    )
    if not rows:
        return mark_safe(html)
    with context.push(tfoot_rows=rows):
        tfoot = engine.get_template(formset.opts.inline_footer_tfoot_template).render(
            context
        )
    controls.tfoot_rendered = True
    return mark_safe(html[:position] + tfoot + html[position:])
