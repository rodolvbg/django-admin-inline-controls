# System checks

Misconfigurations are reported by `manage.py check` (and at startup):

| ID | Problem |
|---|---|
| `admin_inline_controls.E001` | `inline_pagination` is not `"pages"` or `"infinite"`. |
| `admin_inline_controls.E002` | `inline_per_page` is not a positive integer or `None`. |
| `admin_inline_controls.E003` | `inline_pagination = "infinite"` without `inline_per_page`. |
| `admin_inline_controls.E004` | `inline_filter_fields` is a string instead of a list or tuple. |
| `admin_inline_controls.E005` | `inline_filter_fields` refers to a field the model doesn't have. |
| `admin_inline_controls.E006` | `inline_ordering_fields` is not a list, tuple or dict. |
| `admin_inline_controls.E007` | An `inline_ordering_fields` column starts with `-` or contains a comma. |
| `admin_inline_controls.E008` | `inline_save_button = True` but the parent `ModelAdmin` lacks `InlineControlsAdminMixin`. |
| `admin_inline_controls.E009` | An `inline_bulk_actions` entry is not a method of the inline, a callable or a built-in action. |
| `admin_inline_controls.E010` | `inline_bulk_actions` is set but the parent `ModelAdmin` lacks `InlineControlsAdminMixin`. |
| `admin_inline_controls.E020` | `inline_filter_autocomplete` is not `True`, `False` or a list of lookups. |
| `admin_inline_controls.E021` | An `inline_filter_autocomplete` lookup isn't a relation whose model has a `ModelAdmin` with `search_fields` on the site. |
| `admin_inline_controls.E022` | `inline_filter_only_used_values` is not `True`, `False` or a list of lookups. |
| `admin_inline_controls.E011` | `inline_controls_selectors` is not a dict. |
| `admin_inline_controls.E012` | An `inline_controls_selectors` key is unknown, or its value is not a selector or a non-empty list of selectors. |
| `admin_inline_controls.E101` | `inline_pagination = "infinite"` on a nested_admin inline. |
| `admin_inline_controls.E102` | `inline_save_button = True` on a nested_admin inline. |
| `admin_inline_controls.E103` | `inline_bulk_actions` on a nested_admin inline. |
| `admin_inline_controls.E104` | Unfold's `per_page` on an inline with `UnfoldInlineControlsMixin`. |
