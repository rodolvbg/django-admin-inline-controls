import datetime
import re

import pytest
from demo.models import Article, Author, Book
from django.contrib.auth.models import User
from django.template.loader import get_template
from django.test import TestCase
from django.urls import reverse


def custom_inline_html(admin_client, author):
    url = reverse("test_admin:demo_author_change", args=[author.pk])
    html = admin_client.get(url).content.decode()
    start = html.index('id="books-3-inline-controls"')
    return html[html.rindex("<div", 0, start) : html.index('id="books-3-group"')], html


class TestTemplateOverrides(TestCase):
    """Overriding template blocks per inline."""

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

    def test_blocks_can_be_overridden_per_inline(self):
        head, html = custom_inline_html(self.client, self.author)

        assert 'class="inline-controls my-inline"' in head
        assert '<p class="my-intro">Books by this author</p>' in head
        assert ">Search</button>" in head
        assert '<a class="my-help" href="/help/">Help</a>' in head
        assert head.count('<div class="my-filter">') == 1
        # block.super keeps the library's markup inside the override.
        assert 'name="books-3-f-status"' in head
        assert "25 books</span>" in html
        assert len(re.findall(r'<i class="my-page">\s*<', html)) == 5  # 1 2 3 4 5

    def test_other_inlines_keep_the_default_templates(self):
        _, html = custom_inline_html(self.client, self.author)

        assert html.count(">Search</button>") == 1
        assert html.count('class="my-intro"') == 1


BLOCKS = {
    "django_admin_inline_controls/inline.html": [
        "container",
        "container_classes",
        "container_attrs",
        "before_toolbar",
        "toolbar",
        "before_inline",
        "inline",
        "after_inline",
        "footer",
        "after_footer",
        "inline_without_controls",
    ],
    "django_admin_inline_controls/toolbar.html": [
        "toolbar",
        "toolbar_classes",
        "toolbar_start",
        "actions",
        "action_menu",
        "action_label",
        "action_empty_option",
        "action_option",
        "action_button",
        "action_button_label",
        "action_selection",
        "action_status",
        "filters",
        "filter_fields",
        "filter_field",
        "filter_buttons",
        "filter_apply_button",
        "filter_apply_label",
        "filter_clear_button",
        "filter_clear_label",
        "ordering",
        "ordering_label",
        "ordering_column",
        "toolbar_end",
    ],
    "django_admin_inline_controls/footer.html": [
        "footer",
        "footer_classes",
        "footer_start",
        "pagination",
        "infinite",
        "infinite_count",
        "load_more",
        "load_more_label",
        "page_links",
        "page_link",
        "result_count",
        "save",
        "save_status",
        "save_button",
        "save_label",
        "footer_end",
    ],
    "django_admin_inline_controls/inline_response.html": [
        "response",
        "inlines",
    ],
}


@pytest.mark.parametrize(("name", "expected"), BLOCKS.items())
class TestTemplateBlocks:
    """The documented template blocks."""

    def test_every_documented_block_exists(self, name, expected):
        source = get_template(name).template.source

        assert re.findall(r"{% block (\w+) %}", source) == expected
