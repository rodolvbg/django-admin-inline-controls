"""InlinePaginationMixin: pages of rows, as links or loaded on scroll."""

import datetime

from demo.models import Article, Author, Book
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from unittest_parametrize import ParametrizedTestCase, parametrize

from tests.helpers import (
    change_url,
    config,
    formset,
    titles,
)


class TestPagination(ParametrizedTestCase, TestCase):
    """Paginating an inline."""

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

    def test_first_page_has_per_page_rows(self):
        response = self.client.get(change_url(self.author))

        assert response.status_code == 200
        assert titles(response) == [f"Book {n:02d}" for n in range(1, 11)]
        controls = formset(response, "books").inline_controls
        assert controls.total_count == 25
        assert [link.number for link in controls.page_links] == [1, 2, 3]
        assert controls.page_links[0].current

    def test_page_param_selects_page(self):
        response = self.client.get(change_url(self.author, "books-page=3"))

        assert titles(response) == [f"Book {n:02d}" for n in range(21, 26)]

    @parametrize(("page", "expected"), [("abc", "Book 01"), ("99", "Book 21")])
    def test_invalid_or_out_of_range_page(self, page, expected):
        response = self.client.get(change_url(self.author, f"books-page={page}"))

        assert titles(response)[0] == expected

    def test_page_links_keep_other_params(self):
        response = self.client.get(
            change_url(self.author, "books-o=-pages&articles-page=2")
        )
        link = formset(response, "books").inline_controls.page_links[1]

        assert link.url == "?books-o=-pages&articles-page=2&books-page=2"

    def test_inlines_on_the_same_page_are_independent(self):
        response = self.client.get(change_url(self.author, "books-page=2"))

        # "books-2" is the stacked inline of the same model: its own page 1.
        assert titles(response, "books")[0] == "Book 11"
        assert titles(response, "books-2")[0] == "Book 01"

    def test_add_view_renders_without_controls(self):
        response = self.client.get(reverse("admin:demo_author_add"))

        assert response.status_code == 200
        assert formset(response, "books").inline_controls is None
        assert b"data-inline-controls" not in response.content

    def test_plain_inline_renders_like_a_normal_inline(self):
        url = reverse("test_admin:demo_author_change", args=[self.author.pk])
        response = self.client.get(url)
        plain = formset(response, "books-2")

        assert len(plain.initial_forms) == 25
        assert plain.inline_controls.paginator is None
        html = response.content.decode()
        start = html.index('id="books-2-inline-controls"')
        plain_html = html[start : html.index('id="books-3-inline-controls"')]
        assert "inline-controls-toolbar" not in plain_html
        assert "inline-controls-footer" not in plain_html


class TestInfiniteMode(TestCase):
    """Infinite pagination."""

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

    def test_infinite_mode_config(self):
        response = self.client.get(change_url(self.author))
        data = config(response, "articles")

        assert data["mode"] == "infinite"
        assert data["loadedCount"] == 15
        assert data["totalCount"] == 20
        assert data["nextUrl"] == "?articles-page=2"
        assert b"data-inline-controls-more" in response.content

    def test_infinite_mode_last_page_has_no_next(self):
        response = self.client.get(change_url(self.author, "articles-page=2"))

        assert config(response, "articles")["nextUrl"] is None
        assert len(formset(response, "articles").initial_forms) == 5
