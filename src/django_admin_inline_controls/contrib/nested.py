"""django-nested-admin integration. Requires the ``nested`` extra."""

try:
    import nested_admin  # noqa: F401
except ImportError as e:
    raise ImportError(
        "django_admin_inline_controls.contrib.nested requires django-nested-admin. "
        "Install it with: pip install django-admin-inline-controls[nested]"
    ) from e
