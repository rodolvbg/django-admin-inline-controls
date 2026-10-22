"""The package's type aliases."""

from django.test import SimpleTestCase


class TestTypes(SimpleTestCase):
    """The public type aliases."""

    def test_type_aliases_are_importable(self):
        from django_admin_inline_controls import types

        assert set(types.__all__) == {
            "FilterResult",
            "InlineActions",
            "Ordering",
            "OrderingFields",
            "OrderingValue",
            "Selectors",
        }
        assert all(hasattr(types, name) for name in types.__all__)
