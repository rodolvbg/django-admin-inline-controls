"""InlineOrderingMixin: sortable columns."""

import datetime

from demo.models import Article, Author, Book
from django.contrib.auth.models import User
from django.test import TestCase

from tests.helpers import (
    change_url,
    formset,
    pages,
    titles,
)


class TestOrdering(TestCase):
    """Ordering an inline by its columns."""

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

    def test_ordering_descending(self):
        response = self.client.get(change_url(self.author, "books-o=-pages"))

        assert pages(response)[:3] == [250, 240, 230]

    def test_ordering_by_expression(self):
        Book.objects.filter(title="Book 25").update(title="aaa")
        response = self.client.get(change_url(self.author, "books-o=title"))

        # Lower("title") sorts "aaa" before "Book ..." despite the case.
        assert titles(response)[0] == "aaa"

    def test_undeclared_ordering_is_ignored(self):
        response = self.client.get(
            change_url(self.author, "books-o=author__name,-featured,-pages")
        )

        controls = formset(response, "books").inline_controls
        assert controls.ordering == [("pages", True)]
        assert pages(response)[0] == 250

    def test_ordering_columns_urls(self):
        response = self.client.get(
            change_url(self.author, "books-o=-pages&books-page=2")
        )
        columns = {
            c.name: c
            for c in formset(response, "books").inline_controls.ordering_columns
        }

        assert columns["pages"].direction == "descending"
        assert columns["pages"].priority == 1
        assert columns["pages"].toggle_url == "?books-o=pages"
        assert columns["pages"].remove_url == "?"
        # Sorting by a new column makes it primary and resets the page.
        assert columns["title"].toggle_url == "?books-o=title%2C-pages"
        assert columns["title"].priority == 0
        assert columns["title"].label == "Title"
