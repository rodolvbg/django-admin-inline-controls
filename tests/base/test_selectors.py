import datetime
import json

from demo.models import Article, Author, Book
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from unittest_parametrize import ParametrizedTestCase, parametrize

from django_admin_inline_controls.controls import DEFAULT_SELECTORS
from django_admin_inline_controls.mixins import InlineControlsMixin


def make_inline(**attrs):
    return type(
        "BookInline",
        (InlineControlsMixin, admin.TabularInline),
        {"model": Book, "__module__": __name__, **attrs},
    )(Author, admin.site)


class TestSelectors(TestCase):
    """The DOM selectors sent to the JS."""

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

    def test_defaults_are_sent_to_the_js(self):
        response = self.client.get(
            reverse("admin:demo_author_change", args=[self.author.pk])
        )
        controls = response.context["inline_admin_formsets"][0].formset.inline_controls

        assert json.loads(controls.config_json)["selectors"] == DEFAULT_SELECTORS

    def test_overrides_are_merged_over_the_defaults(self):
        inline = make_inline(
            inline_controls_selectors={
                "container": ".card",
                "row_label": [".a", ".b"],
            }
        )
        selectors = inline.get_inline_controls_selectors(None, None)

        assert selectors["container"] == [".card"]
        assert selectors["row_label"] == [".a", ".b"]
        assert selectors["heading"] == DEFAULT_SELECTORS["heading"]
        # The defaults themselves are never modified.
        assert DEFAULT_SELECTORS["container"] == [".inline-group fieldset"]

    def test_themed_inline_uses_its_selectors(self):
        url = reverse("test_admin:demo_author_change", args=[self.author.pk])
        response = self.client.get(url)
        themed = next(
            f.formset
            for f in response.context["inline_admin_formsets"]
            if f.formset.prefix == "books-4"
        )
        selectors = json.loads(themed.inline_controls.config_json)["selectors"]

        assert selectors["column_header"] == ['th[data-col="{name}"]']
        assert selectors["footer_parent"] == DEFAULT_SELECTORS["footer_parent"]


class TestSelectorChecks(ParametrizedTestCase, SimpleTestCase):
    """System checks of the selectors option."""

    @parametrize(
        ("selectors", "error_id"),
        [
            ("container", "admin_inline_controls.E011"),
            ({"nope": ".x"}, "admin_inline_controls.E012"),
            ({"container": ""}, "admin_inline_controls.E012"),
            ({"container": []}, "admin_inline_controls.E012"),
            ({"container": [1]}, "admin_inline_controls.E012"),
        ],
    )
    def test_invalid_selectors(self, selectors, error_id):
        ids = [e.id for e in make_inline(inline_controls_selectors=selectors).check()]

        assert error_id in ids

    def test_valid_selectors_pass_the_checks(self):
        inline = make_inline(
            inline_controls_selectors={"container": ".card", "row_label": [".a", ".b"]}
        )

        assert not [
            e for e in inline.check() if e.id.startswith("admin_inline_controls")
        ]
