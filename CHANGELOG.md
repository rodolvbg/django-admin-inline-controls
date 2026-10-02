# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

### Added

- `InlineControlsMixin` for `TabularInline` and `StackedInline`:
  pagination (page links or infinite scroll), filters (generated from
  lookups or a custom form) and multi-column sorting, with state namespaced
  per inline in the URL.
- In-place refresh of a single inline, re-initializing the admin's inline
  and widget JS; unsaved-changes prompt.
- Saving rows loaded across several pages.
- `inline_save_button` with `InlineControlsAdminMixin`: save a single
  inline without submitting or reloading the rest of the page.
- `inline_actions`: changelist-style actions on the selected rows, with
  "select all" across pages, the `@inline_action` decorator (confirmation
  prompts) and a built-in `delete_selected`.
- `inline_row_actions`: buttons on each saved row (built-in `view` and
  `delete`), compatible with django-inline-actions' signature and per-row
  label/CSS/attribute hooks, run through the inline's action endpoint.
- Template blocks throughout the wrapper, toolbar, footer and response
  templates, and per-inline `inline_controls_toolbar_template` /
  `inline_controls_footer_template`, so they can be extended.
- `contrib.unfold.UnfoldInlineControlsMixin` (`unfold` extra): the controls
  in django-unfold's inlines, with its colors (light and dark); check
  `admin_inline_controls.E104` for Unfold's own `per_page`.
- `form_rows` / `saved_row` selectors, `{prefix}` in selectors, and footer
  rows laid out from the header's `column-<field>` cells: markups without
  row ids or Django's "original" column work too.
- The JS is split per feature: the save button's and the actions' scripts
  load only for inlines that use them.
- `inline_footer_rows` / `inline_footer_scope`: rows of totals, averages…
  below the inline's columns (a `<tfoot>` on tabular inlines), aggregated
  in one query over the filtered rows or the page, rendered by the server
  as the table's own `<tfoot>` (no JS) or a summary line. Raw values in
  `data-value` for the page's JS; format and markup customizable
  (`format_inline_footer_value()`, `tfoot.html` blocks).
- The add view renders the footer rows' `<tfoot>` with empty values, for
  the page's JS.
- `inline_controls_selectors`: where the JS looks in the inline's markup is
  configurable (`DEFAULT_SELECTORS`), for themes and custom inline
  templates; a cancelable `inline-controls:place` event to place the
  toolbar and footer manually.
- Spanish translation (`locale/es`).
- System checks for every option.
- `contrib.filters` (`[filters]` extra): django-filter `FilterSet` support.
- `contrib.nested` (`[nested]` extra): django-nested-admin support.
