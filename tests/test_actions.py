import json

import pytest
from demo.models import Author, Book
from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.http import HttpResponseRedirect
from django.urls import reverse

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


def test_action_config(admin_client, author):
    data = config(admin_client.get(change_url(author)))

    assert data["actionUrl"] == action_url(author)
    assert data["pkName"] == "id"
    assert [action["name"] for action in data["actions"]] == [
        "mark_published",
        "export_csv",
        "delete_selected",
    ]
    delete = data["actions"][2]
    assert delete["confirmation"] == (
        "Delete %(count)s selected books? This cannot be undone."
    )


def test_action_choices_are_rendered(admin_client, author):
    response = admin_client.get(change_url(author))

    assert b"Mark selected books as published" in response.content
    assert b'form="books-inline-controls-actions"' in response.content


def test_run_action_on_selected_rows(admin_client, author):
    pks = book_pks(author, "Book 02", "Book 04")
    response = run(admin_client, author, "mark_published", pks)

    assert response.status_code == 200
    assert status(response) == "done"
    assert b"2 books published." in response.content
    assert Book.objects.filter(pk__in=pks, status="published").count() == 2
    assert Book.objects.filter(author=author, status="draft").count() == 10
    # The messages were shown in this response, not left for the next page.
    next_page = admin_client.get(change_url(author))
    assert not list(next_page.context["messages"])


def test_select_across_uses_the_current_filters(admin_client, author):
    response = run(
        admin_client,
        author,
        "mark_published",
        query="books-f-title__icontains=book 1",
        select_across="1",
    )

    assert b"10 books published." in response.content
    assert Book.objects.filter(author=author, status="draft").count() == 7


def test_selection_is_limited_to_the_parent(admin_client, author, other_author):
    foreign = str(Book.objects.get(author=other_author).pk)
    response = run(admin_client, author, "mark_published", [foreign, "junk"])

    assert status(response) == "error"
    assert b"Items must be selected" in response.content
    assert Book.objects.get(author=other_author).status == "draft"


def test_action_returning_a_response_is_passed_through(admin_client, author):
    response = run(admin_client, author, "export_csv", book_pks(author, "Book 03"))

    assert response["Content-Disposition"] == 'attachment; filename="books.csv"'
    assert response.content.decode().splitlines()[1].startswith("Book 03,")


def test_delete_selected(admin_client, author):
    pks = book_pks(author, "Book 01", "Book 02")
    response = run(admin_client, author, "delete_selected", pks)

    assert status(response) == "done"
    assert b"Deleted 2 books." in response.content
    assert Book.objects.filter(author=author).count() == 23
    entry = LogEntry.objects.get()
    assert entry.object_id == str(author.pk)
    assert json.loads(entry.change_message) == [
        {"deleted": {"name": "book", "object": "Book 01"}},
        {"deleted": {"name": "book", "object": "Book 02"}},
    ]


def test_delete_selected_single_uses_singular(admin_client, author):
    response = run(admin_client, author, "delete_selected", book_pks(author, "Book 05"))

    assert b"Deleted 1 book." in response.content


def test_delete_selected_reports_protected_objects(admin_user, rf, author, monkeypatch):
    from django.db.models import ProtectedError

    book = Book.objects.get(title="Book 01")

    def protected(self, *args, **kwargs):
        raise ProtectedError("protected", {book})

    monkeypatch.setattr(Book, "delete", protected)
    sent = []
    inline = type(
        "Inline", (), {"message_user": lambda s, r, m, level: sent.append((m, level))}
    )()
    delete_selected(inline, rf.post("/"), Book.objects.filter(pk=book.pk))

    assert sent[0][1] == messages.ERROR
    assert "Book 01" in str(sent[0][0])
    assert Book.objects.filter(pk=book.pk).exists()


def test_delete_selected_without_parent_skips_history(rf, author):
    sent = []
    inline = type(
        "Inline",
        (),
        {
            "admin_site": admin.site,
            "message_user": lambda s, r, m, level: sent.append(m),
        },
    )()
    delete_selected(inline, rf.post("/"), Book.objects.filter(title="Book 01"))

    assert not Book.objects.filter(title="Book 01").exists()
    assert not LogEntry.objects.exists()
    assert "Deleted 1 book." in str(sent[0])


def test_unknown_action_is_bad_request(admin_client, author):
    assert run(admin_client, author, "nope", ["1"]).status_code == 400
    assert run(admin_client, author, "", ["1"]).status_code == 400


def test_inline_without_actions_is_404(admin_client, author):
    url = reverse(
        "admin:demo_author_inline_controls_action", args=[author.pk, "books-2"]
    )

    assert admin_client.post(url, {"action": "delete_selected"}).status_code == 404


def test_get_is_not_allowed(admin_client, author):
    assert admin_client.get(action_url(author)).status_code == 405


def test_infinite_inline_rerenders_the_loaded_rows(admin_client, author):
    url = reverse(
        "admin:demo_author_inline_controls_action", args=[author.pk, "articles"]
    )
    pk = str(author.articles.order_by("pk").first().pk)
    response = admin_client.post(
        url,
        {
            "action": "delete_selected",
            "_selected_action": [pk],
            "_inline_controls_loaded": "20",
        },
    )

    assert len(formset(response, "articles").initial_forms) == 19
    assert config(response, "articles")["nextUrl"] is None


def test_invalid_loaded_count_is_ignored(admin_client, author):
    url = reverse(
        "admin:demo_author_inline_controls_action", args=[author.pk, "articles"]
    )
    pk = str(author.articles.order_by("pk").first().pk)
    response = admin_client.post(
        url,
        {
            "action": "delete_selected",
            "_selected_action": [pk],
            "_inline_controls_loaded": "x",
        },
    )

    assert len(formset(response, "articles").initial_forms) == 15


@pytest.fixture
def staff_client(client, db):
    def make(*codenames):
        user = User.objects.create_user("staff", password="x", is_staff=True)
        user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
        client.force_login(user)
        return client

    return make


def test_actions_are_filtered_by_permission(staff_client, author):
    client = staff_client("view_author", "view_book", "change_book")
    data = config(client.get(change_url(author)))

    assert [action["name"] for action in data["actions"]] == [
        "mark_published",
        "export_csv",
    ]
    response = run(client, author, "delete_selected", book_pks(author, "Book 01"))
    assert response.status_code == 400
    assert Book.objects.filter(title="Book 01").exists()


def test_parent_view_permission_required(staff_client, author):
    client = staff_client("change_book", "delete_book")

    assert run(client, author, "mark_published", ["1"]).status_code == 403


def test_actions_without_the_endpoint_are_hidden(admin_user, rf, author):
    site = admin.AdminSite(name="no_actions_site")

    class BookInline(InlineControlsMixin, admin.TabularInline):
        model = Book
        inline_actions = ["delete_selected"]

    request = rf.get("/")
    request.user = admin_user
    formset = BookInline(Author, site).get_formset(request, author)(
        instance=author, prefix="books"
    )

    assert formset.inline_controls.actions == []
    assert formset.inline_controls.action_url is None
    assert formset.inline_controls.has_toolbar is False


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


def test_action_resolution_and_descriptions(admin_user, rf):
    inline = CallableActionInline(Author, admin.site)
    inline.inline_actions = ["plain", standalone, decorated, "delete_selected"]
    request = rf.get("/")
    request.user = admin_user
    actions = inline.get_inline_actions(request, None)

    assert list(actions) == ["plain", "standalone", "decorated", "delete_selected"]
    assert actions["standalone"].description == "Standalone"
    assert actions["decorated"].description == "Admin-decorated"
    assert actions["decorated"].confirmation is None
    assert actions["delete_selected"].description == "Delete selected books"


def test_inline_action_decorator_forms():
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


def make_inline(**attrs):
    return type(
        "BookInline",
        (InlineControlsMixin, admin.TabularInline),
        {"model": Book, "__module__": __name__, **attrs},
    )


def test_check_unknown_action():
    inline_class = make_inline(inline_actions=["nope", 3])
    ids = [e.id for e in inline_class(Author, admin.site).check()]

    assert ids.count("admin_inline_controls.E009") == 2


def test_check_actions_require_admin_mixin():
    site = admin.AdminSite(name="actions_check_site")
    inline_class = make_inline(inline_actions=["delete_selected"])

    @admin.register(Author, site=site)
    class AuthorAdmin(admin.ModelAdmin):
        inlines = [inline_class]

    ids = [e.id for e in inline_class(Author, site).check()]
    assert "admin_inline_controls.E010" in ids


def test_nested_rejects_actions():
    nested_admin = pytest.importorskip("nested_admin")
    from django_admin_inline_controls.contrib.nested import NestedInlineControlsMixin

    class BookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
        model = Book
        inline_actions = ["delete_selected"]

    ids = [e.id for e in BookInline(Author, admin.site).check()]
    assert "admin_inline_controls.E103" in ids


def test_message_user(admin_user, rf):
    from django.contrib.messages.storage.fallback import FallbackStorage

    request = rf.get("/")
    request.session = {}
    request._messages = FallbackStorage(request)
    CallableActionInline(Author, admin.site).message_user(
        request, "hi", messages.WARNING
    )

    assert [(m.message, m.level) for m in request._messages] == [
        ("hi", messages.WARNING)
    ]
