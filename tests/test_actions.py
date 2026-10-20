import datetime
import json
from unittest.mock import patch

import pytest
from demo.models import Article, Author, Book
from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.http import HttpResponseRedirect
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from unittest_parametrize import ParametrizedTestCase, parametrize

from django_admin_inline_controls.actions import delete_selected, inline_action
from django_admin_inline_controls.mixins import InlineControlsMixin
from tests.test_inline_controls import change_url, config, formset


def action_url(author, prefix="books", query=""):
    url = reverse("admin:demo_author_inline_controls_action", args=[author.pk, prefix])
    return f"{url}?{query}" if query else url


def book_pks(author, *titles):
    return [
        str(pk)
        for pk in Book.objects.filter(author=author, title__in=titles).values_list(
            "pk", flat=True
        )
    ]


def run(client, author, action, pks=(), query="", **extra):
    data = {"action": action, "_selected_action": list(pks), **extra}
    return client.post(action_url(author, query=query), data)


def status(response):
    content = response.content.decode()
    return content.split('data-status="')[1].split('"')[0]


def staff_client(client, *codenames):
    user = User.objects.create_user("staff", password="x", is_staff=True)
    user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    client.force_login(user)
    return client


class CallableActionInline(InlineControlsMixin, admin.TabularInline):
    model = Book

    @staticmethod
    def plain(inline, request, queryset):
        return HttpResponseRedirect("/")


def standalone(inline, request, queryset):
    """Not decorated: gets a default description."""


@admin.action(description="Admin-decorated")
def decorated(inline, request, queryset):
    pass


def make_inline(**attrs):
    return type(
        "BookInline",
        (InlineControlsMixin, admin.TabularInline),
        {"model": Book, "__module__": __name__, **attrs},
    )


class TestActionView(ParametrizedTestCase, TestCase):
    """The bulk action endpoint of an inline."""

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

    def test_action_config(self):
        data = config(self.client.get(change_url(self.author)))

        assert data["actionUrl"] == action_url(self.author)
        assert data["pkName"] == "id"
        assert [action["name"] for action in data["bulkActions"]] == [
            "mark_published",
            "export_csv",
            "delete_selected",
        ]
        delete = data["bulkActions"][2]
        assert delete["confirmation"] == (
            "Delete %(count)s selected books? This cannot be undone."
        )

    def test_action_choices_are_rendered(self):
        response = self.client.get(change_url(self.author))

        assert b"Mark selected books as published" in response.content
        assert b'form="books-inline-controls-actions"' in response.content

    def test_run_action_on_selected_rows(self):
        pks = book_pks(self.author, "Book 02", "Book 04")
        response = run(self.client, self.author, "mark_published", pks)

        assert response.status_code == 200
        assert status(response) == "done"
        assert b"2 books published." in response.content
        assert Book.objects.filter(pk__in=pks, status="published").count() == 2
        assert Book.objects.filter(author=self.author, status="draft").count() == 10
        # The messages were shown in this response, not left for the next page.
        next_page = self.client.get(change_url(self.author))
        assert not list(next_page.context["messages"])

    def test_select_across_uses_the_current_filters(self):
        response = run(
            self.client,
            self.author,
            "mark_published",
            query="books-f-title__icontains=book 1",
            select_across="1",
        )

        assert b"10 books published." in response.content
        assert Book.objects.filter(author=self.author, status="draft").count() == 7

    def test_selection_is_limited_to_the_parent(self):
        foreign = str(Book.objects.get(author=self.other_author).pk)
        response = run(self.client, self.author, "mark_published", [foreign, "junk"])

        assert status(response) == "error"
        assert b"Items must be selected" in response.content
        assert Book.objects.get(author=self.other_author).status == "draft"

    def test_action_returning_a_response_is_passed_through(self):
        response = run(
            self.client, self.author, "export_csv", book_pks(self.author, "Book 03")
        )

        assert response["Content-Disposition"] == 'attachment; filename="books.csv"'
        assert response.content.decode().splitlines()[1].startswith("Book 03,")

    @parametrize("action", ["nope", ""], ids=["unknown", "empty"])
    def test_unknown_action_is_bad_request(self, action):
        assert run(self.client, self.author, action, ["1"]).status_code == 400

    def test_inline_without_actions_is_404(self):
        url = reverse(
            "admin:demo_author_inline_controls_action", args=[self.author.pk, "books-2"]
        )

        assert self.client.post(url, {"action": "delete_selected"}).status_code == 404

    def test_get_is_not_allowed(self):
        assert self.client.get(action_url(self.author)).status_code == 405

    def test_infinite_inline_rerenders_the_loaded_rows(self):
        url = reverse(
            "admin:demo_author_inline_controls_action",
            args=[self.author.pk, "articles"],
        )
        pk = str(self.author.articles.order_by("pk").first().pk)
        response = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [pk],
                "_inline_controls_loaded": "20",
            },
        )

        assert len(formset(response, "articles").initial_forms) == 19
        assert config(response, "articles")["nextUrl"] is None

    def test_invalid_loaded_count_is_ignored(self):
        url = reverse(
            "admin:demo_author_inline_controls_action",
            args=[self.author.pk, "articles"],
        )
        pk = str(self.author.articles.order_by("pk").first().pk)
        response = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [pk],
                "_inline_controls_loaded": "x",
            },
        )

        assert len(formset(response, "articles").initial_forms) == 15


class TestDeleteSelected(TestCase):
    """The built-in delete_selected action."""

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

    def test_delete_selected(self):
        pks = book_pks(self.author, "Book 01", "Book 02")
        response = run(self.client, self.author, "delete_selected", pks)

        assert status(response) == "done"
        assert b"Deleted 2 books." in response.content
        assert Book.objects.filter(author=self.author).count() == 23
        entry = LogEntry.objects.get()
        assert entry.object_id == str(self.author.pk)
        assert json.loads(entry.change_message) == [
            {"deleted": {"name": "book", "object": "Book 01"}},
            {"deleted": {"name": "book", "object": "Book 02"}},
        ]

    def test_delete_selected_single_uses_singular(self):
        response = run(
            self.client,
            self.author,
            "delete_selected",
            book_pks(self.author, "Book 05"),
        )

        assert b"Deleted 1 book." in response.content

    def test_delete_selected_reports_protected_objects(self):
        from django.db.models import ProtectedError

        book = Book.objects.get(title="Book 01")

        def protected(self, *args, **kwargs):
            raise ProtectedError("protected", {book})

        sent = []
        inline = type(
            "Inline",
            (),
            {"message_user": lambda s, r, m, level: sent.append((m, level))},
        )()
        with patch.object(Book, "delete", protected):
            delete_selected(
                inline, RequestFactory().post("/"), Book.objects.filter(pk=book.pk)
            )

        assert sent[0][1] == messages.ERROR
        assert "Book 01" in str(sent[0][0])
        assert Book.objects.filter(pk=book.pk).exists()

    def test_delete_selected_without_parent_skips_history(self):
        sent = []
        inline = type(
            "Inline",
            (),
            {
                "admin_site": admin.site,
                "message_user": lambda s, r, m, level: sent.append(m),
            },
        )()
        delete_selected(
            inline, RequestFactory().post("/"), Book.objects.filter(title="Book 01")
        )

        assert not Book.objects.filter(title="Book 01").exists()
        assert not LogEntry.objects.exists()
        assert "Deleted 1 book." in str(sent[0])


class TestActionPermissions(TestCase):
    """Permissions of bulk actions."""

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

    def test_actions_are_filtered_by_permission(self):
        client = staff_client(self.client, "view_author", "view_book", "change_book")
        data = config(client.get(change_url(self.author)))

        assert [action["name"] for action in data["bulkActions"]] == [
            "mark_published",
            "export_csv",
        ]
        response = run(
            client, self.author, "delete_selected", book_pks(self.author, "Book 01")
        )
        assert response.status_code == 400
        assert Book.objects.filter(title="Book 01").exists()

    def test_parent_view_permission_required(self):
        client = staff_client(self.client, "change_book", "delete_book")

        assert run(client, self.author, "mark_published", ["1"]).status_code == 403

    def test_actions_without_the_endpoint_are_hidden(self):
        site = admin.AdminSite(name="no_actions_site")

        class BookInline(InlineControlsMixin, admin.TabularInline):
            model = Book
            inline_bulk_actions = ["delete_selected"]

        request = RequestFactory().get("/")
        request.user = self.user
        formset = BookInline(Author, site).get_formset(request, self.author)(
            instance=self.author, prefix="books"
        )

        assert formset.inline_controls.bulk_actions == []
        assert formset.inline_controls.action_url is None
        assert formset.inline_controls.has_toolbar is False


class TestInlineActions(TestCase):
    """Resolving and declaring inline actions."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )

    def test_action_resolution_and_descriptions(self):
        inline = CallableActionInline(Author, admin.site)
        inline.inline_bulk_actions = ["plain", standalone, decorated, "delete_selected"]
        request = RequestFactory().get("/")
        request.user = self.user
        actions = inline.get_inline_bulk_actions(request, None)

        assert list(actions) == ["plain", "standalone", "decorated", "delete_selected"]
        assert actions["standalone"].description == "Standalone"
        assert actions["decorated"].description == "Admin-decorated"
        assert actions["decorated"].confirmation is None
        assert actions["delete_selected"].description == "Delete selected books"

    def test_inline_action_decorator_forms(self):
        @inline_action
        def bare(inline, request, queryset):
            pass

        @inline_action(
            description="D", confirmation="Sure %(count)s?", permissions=["change"]
        )
        def full(inline, request, queryset):
            pass

        assert not hasattr(bare, "confirmation")
        assert full.short_description == "D"
        assert full.confirmation == "Sure %(count)s?"
        assert full.allowed_permissions == ["change"]

    def test_message_user(self):
        from django.contrib.messages.storage.fallback import FallbackStorage

        request = RequestFactory().get("/")
        request.session = {}
        request._messages = FallbackStorage(request)
        CallableActionInline(Author, admin.site).message_user(
            request, "hi", messages.WARNING
        )

        assert [(m.message, m.level) for m in request._messages] == [
            ("hi", messages.WARNING)
        ]


class TestActionChecks(SimpleTestCase):
    """System checks of the bulk actions option."""

    def test_check_unknown_action(self):
        inline_class = make_inline(inline_bulk_actions=["nope", 3])
        ids = [e.id for e in inline_class(Author, admin.site).check()]

        assert ids.count("admin_inline_controls.E009") == 2

    def test_check_actions_require_admin_mixin(self):
        site = admin.AdminSite(name="actions_check_site")
        inline_class = make_inline(inline_bulk_actions=["delete_selected"])

        @admin.register(Author, site=site)
        class AuthorAdmin(admin.ModelAdmin):
            inlines = [inline_class]

        ids = [e.id for e in inline_class(Author, site).check()]
        assert "admin_inline_controls.E010" in ids

    def test_nested_rejects_actions(self):
        nested_admin = pytest.importorskip("nested_admin")
        from django_admin_inline_controls.contrib.nested import (
            NestedInlineControlsMixin,
        )

        class BookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
            model = Book
            inline_bulk_actions = ["delete_selected"]

        ids = [e.id for e in BookInline(Author, admin.site).check()]
        assert "admin_inline_controls.E103" in ids
