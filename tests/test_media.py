import re

from demo.models import Author, Book
from django.contrib import admin

from django_admin_inline_controls.mixins import InlineControlsMixin

CORE = "django_admin_inline_controls/js/core.js"
SAVE = "django_admin_inline_controls/js/save.js"
ACTIONS = "django_admin_inline_controls/js/actions.js"


def scripts(media):
    """This library's scripts in ``media``, in the order they load."""
    return re.findall(r"django_admin_inline_controls/js/[\w]+\.js", str(media))


def inline_js(**options):
    inline_class = type(
        "Inline", (InlineControlsMixin, admin.TabularInline), {"model": Book, **options}
    )
    inline = inline_class(Author, admin.AdminSite(name="media_site"))
    return scripts(inline.media)


def test_only_the_core_script_by_default():
    assert inline_js() == [CORE]


def test_features_add_their_scripts():
    assert inline_js(inline_save_button=True) == [CORE, SAVE]
    assert inline_js(inline_bulk_actions=["delete_selected"]) == [CORE, ACTIONS]
    assert inline_js(
        inline_save_button=True, inline_bulk_actions=["delete_selected"]
    ) == [
        CORE,
        SAVE,
        ACTIONS,
    ]


def test_several_inlines_merge_without_duplicates():
    media = (
        type("A", (InlineControlsMixin, admin.TabularInline), {"model": Book})(
            Author, admin.site
        ).media
        + type(
            "B",
            (InlineControlsMixin, admin.TabularInline),
            {"model": Book, "inline_bulk_actions": ["delete_selected"]},
        )(Author, admin.site).media
        + type(
            "C",
            (InlineControlsMixin, admin.TabularInline),
            {
                "model": Book,
                "inline_save_button": True,
                "inline_bulk_actions": ["delete_selected"],
            },
        )(Author, admin.site).media
    )
    assert scripts(media) == [CORE, SAVE, ACTIONS]


def test_the_change_form_loads_only_what_its_inlines_use(admin_client, author):
    from django.urls import reverse

    html = admin_client.get(
        reverse("test_admin:demo_author_change", args=[author.pk])
    ).content.decode()
    assert CORE in html
    assert ACTIONS in html  # ThemedBookInline has actions
    assert SAVE not in html
