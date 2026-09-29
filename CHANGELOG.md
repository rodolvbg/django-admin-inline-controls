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
- System checks for every option.
- `contrib.filters` (`[filters]` extra): django-filter `FilterSet` support.
- `contrib.nested` (`[nested]` extra): django-nested-admin support.
