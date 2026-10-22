"""InlineControlsMixin and InlineControlsAdminMixin: one mixin per feature."""

from demo.models import Author, Book
from django.contrib import admin
from django.test import SimpleTestCase

from django_admin_inline_controls import features
from django_admin_inline_controls.mixins import (
    InlineControlsAdminMixin,
    InlineControlsMixin,
)


def inline(**attrs):
    cls = type(
        "BookInline",
        (InlineControlsMixin, admin.TabularInline),
        {"model": Book, **attrs},
    )
    return cls(Author, admin.site)


class TestFeatures(SimpleTestCase):
    def test_the_inline_is_every_feature(self):
        for feature in (
            features.InlinePaginationMixin,
            features.InlineOrderingMixin,
            features.InlineFiltersMixin,
            features.InlineSaveMixin,
            features.InlineBulkActionsMixin,
            features.InlineControlsBaseMixin,
        ):
            assert issubclass(InlineControlsMixin, feature), feature

    def test_the_parent_admin_is_every_endpoint(self):
        assert issubclass(InlineControlsAdminMixin, features.InlineSaveAdminMixin)
        assert issubclass(
            InlineControlsAdminMixin, features.InlineBulkActionsAdminMixin
        )

    def test_each_feature_adds_its_script_in_order(self):
        assert inline().get_inline_controls_scripts() == [
            "django_admin_inline_controls/js/core.js"
        ]
        both = inline(inline_save_button=True, inline_bulk_actions=["delete_selected"])
        assert both.get_inline_controls_scripts() == [
            "django_admin_inline_controls/js/core.js",
            "django_admin_inline_controls/js/save.js",
            "django_admin_inline_controls/js/actions.js",
        ]

    def test_the_parents_endpoints_save_first(self):
        class AuthorAdmin(InlineControlsAdminMixin, admin.ModelAdmin):
            pass

        names = [p.name for p in AuthorAdmin(Author, admin.site).get_urls()[:2]]
        assert names == [
            "demo_author_inline_controls_save",
            "demo_author_inline_controls_action",
        ]
