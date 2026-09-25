"""django-filter integration. Requires the ``filters`` extra."""

try:
    import django_filters  # noqa: F401
except ImportError as e:
    raise ImportError(
        "django_admin_inline_controls.contrib.filters requires django-filter. "
        "Install it with: pip install django-admin-inline-controls[filters]"
    ) from e
