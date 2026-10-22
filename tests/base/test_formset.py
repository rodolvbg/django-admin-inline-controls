"""InlineControlsBaseMixin: the inline's formset, saved with the page."""

import datetime

from demo.models import Article, Author, Book
from django.contrib.auth.models import User
from django.test import TestCase

from tests.helpers import (
    change_url,
    config,
    post_data,
)


class TestSavingRows(TestCase):
    """Saving the change form with paginated rows."""

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
        cls.other_author = Author.objects.create(name="Other")
        Book.objects.create(author=cls.other_author, title="Other book", pages=1)

    def setUp(self):
        self.client.force_login(self.user)

    def test_save_rows_of_a_later_page(self):
        page_two = list(Book.objects.filter(author=self.author).order_by("pk")[10:20])
        page_two[3].title = "Edited"
        response = self.client.post(
            change_url(self.author, "books-page=2"),
            post_data(self.author, books=page_two),
        )

        assert response.status_code == 302
        assert Book.objects.get(pk=page_two[3].pk).title == "Edited"
        assert Book.objects.filter(author=self.author).count() == 25

    def test_save_rows_loaded_across_pages(self):
        # Infinite scroll: 20 articles from two "pages" submitted together.
        articles = list(Article.objects.filter(author=self.author).order_by("pk"))
        articles[17].title = "Loaded later"
        response = self.client.post(
            change_url(self.author), post_data(self.author, articles=articles)
        )

        assert response.status_code == 302
        assert Article.objects.get(pk=articles[17].pk).title == "Loaded later"

    def test_save_ignores_rows_of_another_parent(self):
        foreign = Book.objects.get(author=self.other_author)
        foreign.title = "Hijacked"
        self.client.post(
            change_url(self.author), post_data(self.author, books=[foreign])
        )

        foreign.refresh_from_db()
        assert foreign.title == "Other book"
        assert foreign.author == self.other_author

    def test_invalid_submitted_pk_is_ignored(self):
        data = post_data(
            self.author, books=list(Book.objects.filter(author=self.author)[:1])
        )
        data["books-0-id"] = "not-a-number"
        response = self.client.post(change_url(self.author), data)

        assert response.status_code == 200  # re-rendered with a form error

    def test_infinite_mode_after_validation_error_continues_after_loaded_rows(self):
        articles = list(Article.objects.filter(author=self.author).order_by("pk")[:15])
        data = post_data(self.author, articles=articles)
        data["articles-0-words"] = "-1"  # invalid PositiveIntegerField
        response = self.client.post(change_url(self.author), data)

        assert response.status_code == 200
        assert config(response, "articles")["loadedCount"] == 15
        assert config(response, "articles")["nextUrl"] == "?articles-page=2"
