"""Server-side rendering of the footer rows inside the inline's own table."""

from __future__ import annotations

import re

from django import template
from django.utils.safestring import SafeString, mark_safe

from django_admin_inline_controls.controls import empty_footer_rows, layout_tfoot_rows

register = template.Library()


def _header_columns(html: str) -> tuple[dict[str, int], int]:
    """Position of each field's column in the table's header row (its
    ``th.column-<name>``), and the row's width, as rendered: the leading
    columns (Django's narrow "original" one) and the trailing ones vary with
    the Django version, the theme and the delete permission. Hidden headers
    take no room."""
    head = re.search(r"<thead.*?</thead>", html, re.S)
    positions: dict[str, int] = {}
    width = 0
    for attrs in re.findall(r"<th\b([^>]*)>", head.group() if head else ""):
        classes = re.search(r'class="([^"]*)"', attrs)
        names = classes.group(1).split() if classes else []
        if "hidden" in names:
            continue
        for name in names:
            if name.startswith("column-"):
                positions.setdefault(name.removeprefix("column-"), width)
        span = re.search(r'colspan="(\d+)"', attrs)
        width += int(span.group(1)) if span else 1
    return positions, width


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
    if not formset.opts.inline_footer_tfoot:
        return mark_safe(html)
    if controls:
        footer_rows = controls.footer_rows
    else:
        # The add view: the rows' structure, without values.
        request = getattr(formset.formset, "inline_controls_request", None)
        footer_rows = empty_footer_rows(formset.opts, request)
    # Last in the table: if it has its own <tfoot> (Unfold's "Add another"),
    # that one stays the table's footer and these rows show above it.
    position = html.rfind("</table>")
    rows = (
        layout_tfoot_rows(footer_rows, *_header_columns(html))
        if footer_rows and position != -1
        else None
    )
    if not rows:
        return mark_safe(html)
    with context.push(tfoot_rows=rows):
        tfoot = engine.get_template(formset.opts.inline_footer_tfoot_template).render(
            context
        )
    if controls:
        controls.tfoot_rendered = True
    return mark_safe(html[:position] + tfoot + html[position:])
