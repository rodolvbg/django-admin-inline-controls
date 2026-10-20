import datetime

import pytest
from demo.models import Article, Author, Book
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory, TestCase
from django.urls import reverse
from unittest_parametrize import ParametrizedTestCase, parametrize

from django_admin_inline_controls.mixins import InlineControlsMixin
from tests.test_inline_controls import change_url, config, formset, post_data


def save_url(author, prefix="books", query=""):
    url = reverse("admin:demo_author_inline_controls_save", args=[author.pk, prefix])
    return f"{url}?{query}" if query else url


def inline_data(author, prefix, rows):
    """Only one inline's fields, as the JS sends them."""
    data = post_data(author, **{"books" if prefix == "books" else "articles": rows})
    return {key: value for key, value in data.items() if key.startswith(f"{prefix}-")}


def staff_client(client, *codenames):
    user = User.objects.create_user("staff", password="x", is_staff=True)
    user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    client.force_login(user)
    return client


class TestSaveInlineView(ParametrizedTestCase, TestCase):
    """The save endpoint of an inline."""

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

    def test_save_button_config(self):
        response = self.client.get(change_url(self.author))

        assert config(response)["saveUrl"] == save_url(self.author)
        assert config(response, "articles")["saveUrl"] == save_url(
            self.author, "articles"
        )
        assert config(response, "books-2")["saveUrl"] is None
        assert b"data-inline-controls-save" in response.content
        assert b"Save books" in response.content

    def test_save_only_the_inline(self):
        rows = list(Book.objects.filter(author=self.author).order_by("pk")[10:20])
        rows[0].title = "Saved alone"
        data = inline_data(self.author, "books", rows)
        response = self.client.post(save_url(self.author, query="books-page=2"), data)

        assert response.status_code == 200
        assert b'data-status="saved"' in response.content
        assert b'id="books-inline-controls"' in response.content
        assert Book.objects.get(pk=rows[0].pk).title == "Saved alone"
        # Re-rendered with the same page, from the query string.
        assert formset(response, "books").inline_controls.page.number == 2
        entry = LogEntry.objects.get()
        assert entry.object_id == str(self.author.pk)
        assert "Saved alone" in entry.get_change_message()

    def test_save_ignores_parent_fields(self):
        data = inline_data(
            self.author, "books", list(Book.objects.filter(author=self.author)[:1])
        )
        data["name"] = "Changed parent"
        self.client.post(save_url(self.author), data)

        self.author.refresh_from_db()
        assert self.author.name == "Author"

    def test_save_with_no_changes_logs_nothing(self):
        rows = list(Book.objects.filter(author=self.author).order_by("pk")[:10])
        self.client.post(save_url(self.author), inline_data(self.author, "books", rows))

        assert not LogEntry.objects.exists()

    def test_save_adds_and_deletes(self):
        rows = list(Book.objects.filter(author=self.author).order_by("pk")[:10])
        data = inline_data(self.author, "books", rows)
        data["books-TOTAL_FORMS"] = "11"
        data.update(
            {
                "books-0-DELETE": "on",
                "books-10-author": str(self.author.pk),
                "books-10-title": "Added inline",
                "books-10-status": "draft",
                "books-10-pages": "3",
            }
        )
        response = self.client.post(save_url(self.author), data)

        assert b'data-status="saved"' in response.content
        assert not Book.objects.filter(pk=rows[0].pk).exists()
        assert Book.objects.filter(author=self.author, title="Added inline").exists()

    def test_invalid_inline_is_returned_with_errors(self):
        rows = list(Book.objects.filter(author=self.author).order_by("pk")[:10])
        rows[0].title = "Not saved"
        data = inline_data(self.author, "books", rows)
        data["books-1-pages"] = "-1"
        response = self.client.post(save_url(self.author), data)

        assert response.status_code == 200
        assert b'data-status="invalid"' in response.content
        assert formset(response, "books").errors[1]
        assert Book.objects.filter(title="Not saved").count() == 0

    def test_infinite_inline_rerenders_the_loaded_pages(self):
        rows = list(Article.objects.filter(author=self.author).order_by("pk"))
        data = inline_data(self.author, "articles", rows)  # both pages were loaded
        response = self.client.post(save_url(self.author, "articles"), data)

        assert len(formset(response, "articles").initial_forms) == 20
        assert config(response, "articles")["loadedCount"] == 20
        assert config(response, "articles")["nextUrl"] is None

    def test_infinite_inline_after_one_page(self):
        rows = list(Article.objects.filter(author=self.author).order_by("pk")[:15])
        response = self.client.post(
            save_url(self.author, "articles"),
            inline_data(self.author, "articles", rows),
        )

        assert len(formset(response, "articles").initial_forms) == 15
        assert config(response, "articles")["nextUrl"] == "?articles-page=2"

    @parametrize("prefix", ["nope", "books-2"])
    def test_unknown_prefix_or_inline_without_button_is_404(self, prefix):
        response = self.client.post(save_url(self.author, prefix), {})

        assert response.status_code == 404

    def test_unknown_object_is_404(self):
        url = reverse("admin:demo_author_inline_controls_save", args=[999, "books"])

        assert self.client.post(url, {}).status_code == 404

    def test_get_is_not_allowed(self):
        assert self.client.get(save_url(self.author)).status_code == 405


class TestSaveInlinePermissions(ParametrizedTestCase, TestCase):
    """Permissions of the save endpoint."""

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

    @parametrize(
        "codenames",
        [(("view_author", "change_book"),), (("change_author", "view_book"),)],
        ids=["parent_change_missing", "inline_change_missing"],
    )
    def test_change_permissions_required(self, codenames):
        client = staff_client(self.client, *codenames)

        assert client.post(save_url(self.author), {}).status_code == 403

    def test_delete_only_permission_skips_view_only_rows(self, staff_client):
        client = staff_client(self.client, "change_author", "view_book", "delete_book")
        rows = list(Book.objects.filter(author=self.author).order_by("pk")[:10])
        data = {
            key: value
            for key, value in inline_data(self.author, "books", rows).items()
            if key.endswith(("-id", "-author", "_FORMS"))
        }
        data["books-2-DELETE"] = "on"
        response = client.post(save_url(self.author), data)

        assert b'data-status="saved"' in response.content
        assert not Book.objects.filter(pk=rows[2].pk).exists()
        assert Book.objects.filter(author=self.author).count() == 24


class TestSaveButtonChecks(TestCase):
    """Save button availability and its system checks."""

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

    def test_no_save_button_without_the_admin_mixin(self):

        site = admin.AdminSite(name="unrouted_site")

        class BookInline(InlineControlsMixin, admin.TabularInline):
            model = Book
            inline_save_button = True

        request = RequestFactory().get("/")
        request.user = self.user
        inline = BookInline(Author, site)
        formset = inline.get_formset(request, self.author)(
            instance=self.author, prefix="books"
        )

        assert formset.inline_controls.save_url is None
        assert formset.inline_controls.has_footer is False

    def test_check_requires_admin_mixin(self):
        site = admin.AdminSite(name="check_site")

        class BookInline(InlineControlsMixin, admin.TabularInline):
            model = Book
            inline_save_button = True

        @admin.register(Author, site=site)
        class AuthorAdmin(admin.ModelAdmin):
            inlines = [BookInline]

        ids = [error.id for error in BookInline(Author, site).check()]
        assert "admin_inline_controls.E008" in ids

    def test_nested_rejects_save_button(self):
        nested_admin = pytest.importorskip("nested_admin")
        from django_admin_inline_controls.contrib.nested import (
            NestedInlineControlsMixin,
        )

        class BookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
            model = Book
            inline_save_button = True

        ids = [error.id for error in BookInline(Author, admin.site).check()]
        assert "admin_inline_controls.E102" in ids
