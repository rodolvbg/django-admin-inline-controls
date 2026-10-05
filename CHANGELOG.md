# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-05

First release.

### Added

- **`InlineControlsMixin`** for `TabularInline` and `StackedInline`:
  - pagination, with page links or infinite scroll, and saving rows loaded
    across several pages;
  - filters, generated from lookups or from a form of yours
    (`contrib.filters` for a django-filter `FilterSet`);
  - multi-column sorting from the column headers;
  - state namespaced per inline in the URL, and in-place refresh of a
    single inline (re-initializing the admin's inline and widget JS) with
    an unsaved-changes prompt.
- **Saving one inline** (`inline_save_button`, with
  `InlineControlsAdminMixin` on the parent): without submitting or
  reloading the rest of the page, recorded in the parent's history.
- **Bulk actions** (`inline_bulk_actions`): like the changelist's, on the
  selected rows, with "select all" across pages, the `@inline_action`
  decorator (permissions, confirmation prompts) and a built-in
  `delete_selected`.
- **Row actions** (`inline_actions`): buttons on each saved row, with
  django-inline-actions' API — the `(request, obj, parent_obj)` signature,
  `get_inline_actions()`, per-row `get_<action>_label/css/attr()` hooks and
  the `ViewAction`, `DeleteAction` and `DefaultActionsMixin` mixins — run
  without submitting the change form, with the permissions checked by the
  server.
- **Footer rows** (`inline_footer_rows`, `inline_footer_scope`): totals,
  averages… aggregated in one query over the filtered rows or the page,
  rendered by the server as the table's `<tfoot>` (also in the add view,
  empty) or as a summary line; raw values in `data-*` attributes for the
  page's JS; format (`format_inline_footer_value()`) and markup
  (`tfoot.html`) customizable.
- **Customizable markup:** template blocks throughout, per-inline
  templates, and `inline_controls_selectors` (`DEFAULT_SELECTORS`) for
  themes and custom inline templates, plus the `inline-controls:place` and
  `inline-controls:updated` events.
- **django-unfold** support (`contrib.unfold`, `unfold` extra): the
  controls in Unfold's inlines with its colors, light and dark.
- **django-nested-admin** support (`contrib.nested`, `nested` extra).
- Only the scripts an inline uses are loaded (`core.js`, `save.js`,
  `actions.js`).
- Spanish translation, and system checks for every option.
- Django 4.2 – 6.1, Python 3.10+.
