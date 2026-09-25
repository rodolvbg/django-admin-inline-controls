from django_admin_inline_controls.mixins import ExampleMixin


def test_example_mixin_is_a_model_admin_subclass():
    from django.contrib import admin

    assert issubclass(ExampleMixin, admin.ModelAdmin)
