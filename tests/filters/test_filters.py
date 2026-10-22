"""InlineFiltersMixin: the filter form above the rows."""

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


class TestFilters(ParametrizedTestCase, TestCase):
    """Filtering an inline."""

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

    @parametrize(
        ("query", "expected_count"),
        [
            ("books-f-status=published", 13),
            ("books-f-title__icontains=book 1", 10),
            ("books-f-featured=true", 5),
            ("books-f-featured=false", 20),
            ("books-f-published__gte=2020-01-20", 7),
            ("books-f-status=published&books-f-featured=true", 3),
        ],
    )
    def test_filters(self, query, expected_count):
        response = self.client.get(change_url(self.author, query))

        assert formset(response, "books").inline_controls.total_count == expected_count

    def test_invalid_filter_value_is_ignored_and_reported(self):
        response = self.client.get(
            change_url(self.author, "books-f-published__gte=nope")
        )
        controls = formset(response, "books").inline_controls

        assert controls.total_count == 25
        assert "published__gte" in controls.filter_form.errors

    def test_filter_widgets_are_detached_from_the_change_form(self):
        response = self.client.get(change_url(self.author))

        assert b'form="books-inline-controls-filters"' in response.content
        assert config(response)["filterParams"] == [
            "books-f-title__icontains",
            "books-f-status",
            "books-f-publisher",
            "books-f-featured",
            "books-f-published__gte",
        ]

    def test_filtering_resets_pagination_in_links(self):
        response = self.client.get(change_url(self.author, "books-f-status=draft"))

        assert formset(response, "books").inline_controls.is_filtered
        assert b"data-inline-controls-clear" in response.content

    def test_custom_filter_form(self):
        url = reverse("test_admin:demo_author_change", args=[self.author.pk])
        response = self.client.get(f"{url}?books-f-q=book 2&books-f-status=published")

        assert titles(response) == ["Book 21", "Book 23", "Book 25"]
