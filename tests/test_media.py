import datetime
import re

from demo.models import Article, Author, Book
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase
from unittest_parametrize import ParametrizedTestCase, parametrize

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


class TestInlineControlsMedia(ParametrizedTestCase, TestCase):
    """The scripts an inline loads."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        cls.author = Author.objects.create(name="Author")
        statuses = [Book.Status.DRAFT, Book.Status.PUBLISHED]
        Book.objects.bulk_create(
            Book(
                author=cls.author,
                title=f"Book {n:02d}",
                status=statuses[n % 2],
                published=datetime.date(2020, 1, 1) + datetime.timedelta(days=n),
                pages=10 * n,
                featured=n % 5 == 0,
            )
            for n in range(1, 26)
        )
        Article.objects.bulk_create(
            Article(author=cls.author, title=f"Article {n:02d}", words=n)
            for n in range(1, 21)
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_only_the_core_script_by_default(self):
        assert inline_js() == [CORE]

    @parametrize(
        ("options", "expected"),
        [
            ({"inline_save_button": True}, [CORE, SAVE]),
            ({"inline_bulk_actions": ["delete_selected"]}, [CORE, ACTIONS]),
            (
                {
                    "inline_save_button": True,
                    "inline_bulk_actions": ["delete_selected"],
                },
                [CORE, SAVE, ACTIONS],
            ),
        ],
        ids=["save", "actions", "save_and_actions"],
    )
    def test_features_add_their_scripts(self, options, expected):
        assert inline_js(**options) == expected

    def test_several_inlines_merge_without_duplicates(self):
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

    def test_the_change_form_loads_only_what_its_inlines_use(self):
        from django.urls import reverse

        html = self.client.get(
            reverse("test_admin:demo_author_change", args=[self.author.pk])
        ).content.decode()
        assert CORE in html
        assert ACTIONS in html  # ThemedBookInline has actions
        assert SAVE not in html
