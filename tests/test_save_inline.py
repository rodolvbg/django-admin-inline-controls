import pytest
from demo.models import Article, Author, Book
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.urls import reverse

from django_admin_inline_controls.mixins import InlineControlsMixin
from tests.test_inline_controls import change_url, config, formset, post_data


def save_url(author, prefix="books", query=""):
    url = reverse("admin:demo_author_inline_controls_save", args=[author.pk, prefix])
    return f"{url}?{query}" if query else url


def inline_data(author, prefix, rows):
    """Only one inline's fields, as the JS sends them."""
    data = post_data(author, **{"books" if prefix == "books" else "articles": rows})
    return {key: value for key, value in data.items() if key.startswith(f"{prefix}-")}


def test_save_button_config(admin_client, author):
    response = admin_client.get(change_url(author))

    assert config(response)["saveUrl"] == save_url(author)
    assert config(response, "articles")["saveUrl"] == save_url(author, "articles")
    assert config(response, "books-2")["saveUrl"] is None
    assert b"data-inline-controls-save" in response.content
    assert b"Save books" in response.content


def test_save_only_the_inline(admin_client, author):
    rows = list(Book.objects.filter(author=author).order_by("pk")[10:20])
    rows[0].title = "Saved alone"
    data = inline_data(author, "books", rows)
    response = admin_client.post(save_url(author, query="books-page=2"), data)

    assert response.status_code == 200
    assert b'data-status="saved"' in response.content
    assert b'id="books-inline-controls"' in response.content
    assert Book.objects.get(pk=rows[0].pk).title == "Saved alone"
    # Re-rendered with the same page, from the query string.
    assert formset(response, "books").inline_controls.page.number == 2
    entry = LogEntry.objects.get()
    assert entry.object_id == str(author.pk)
    assert "Saved alone" in entry.get_change_message()


def test_save_ignores_parent_fields(admin_client, author):
    data = inline_data(author, "books", list(Book.objects.filter(author=author)[:1]))
    data["name"] = "Changed parent"
    admin_client.post(save_url(author), data)

    author.refresh_from_db()
    assert author.name == "Author"


def test_save_with_no_changes_logs_nothing(admin_client, author):
    rows = list(Book.objects.filter(author=author).order_by("pk")[:10])
    admin_client.post(save_url(author), inline_data(author, "books", rows))

    assert not LogEntry.objects.exists()


def test_save_adds_and_deletes(admin_client, author):
    rows = list(Book.objects.filter(author=author).order_by("pk")[:10])
    data = inline_data(author, "books", rows)
    data["books-TOTAL_FORMS"] = "11"
    data.update(
        {
            "books-0-DELETE": "on",
            "books-10-author": str(author.pk),
            "books-10-title": "Added inline",
            "books-10-status": "draft",
            "books-10-pages": "3",
        }
    )
    response = admin_client.post(save_url(author), data)

    assert b'data-status="saved"' in response.content
    assert not Book.objects.filter(pk=rows[0].pk).exists()
    assert Book.objects.filter(author=author, title="Added inline").exists()


def test_invalid_inline_is_returned_with_errors(admin_client, author):
    rows = list(Book.objects.filter(author=author).order_by("pk")[:10])
    rows[0].title = "Not saved"
    data = inline_data(author, "books", rows)
    data["books-1-pages"] = "-1"
    response = admin_client.post(save_url(author), data)

    assert response.status_code == 200
    assert b'data-status="invalid"' in response.content
    assert formset(response, "books").errors[1]
    assert Book.objects.filter(title="Not saved").count() == 0


def test_infinite_inline_rerenders_the_loaded_pages(admin_client, author):
    rows = list(Article.objects.filter(author=author).order_by("pk"))
    data = inline_data(author, "articles", rows)  # both pages were loaded
    response = admin_client.post(save_url(author, "articles"), data)

    assert len(formset(response, "articles").initial_forms) == 20
    assert config(response, "articles")["loadedCount"] == 20
    assert config(response, "articles")["nextUrl"] is None


def test_infinite_inline_after_one_page(admin_client, author):
    rows = list(Article.objects.filter(author=author).order_by("pk")[:15])
    response = admin_client.post(
        save_url(author, "articles"), inline_data(author, "articles", rows)
    )

    assert len(formset(response, "articles").initial_forms) == 15
    assert config(response, "articles")["nextUrl"] == "?articles-page=2"


@pytest.mark.parametrize("prefix", ["nope", "books-2"])
def test_unknown_prefix_or_inline_without_button_is_404(admin_client, author, prefix):
    response = admin_client.post(save_url(author, prefix), {})

    assert response.status_code == 404


def test_unknown_object_is_404(admin_client, db):
    url = reverse("admin:demo_author_inline_controls_save", args=[999, "books"])

    assert admin_client.post(url, {}).status_code == 404


def test_get_is_not_allowed(admin_client, author):
    assert admin_client.get(save_url(author)).status_code == 405


@pytest.fixture
def staff_client(client, db):
    def make(*codenames):
        user = User.objects.create_user("staff", password="x", is_staff=True)
        user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
        client.force_login(user)
        return client

    return make


def test_parent_change_permission_required(staff_client, author):
    client = staff_client("view_author", "change_book")

    assert client.post(save_url(author), {}).status_code == 403


def test_inline_permission_required(staff_client, author):
    client = staff_client("change_author", "view_book")

    assert client.post(save_url(author), {}).status_code == 403


def test_delete_only_permission_skips_view_only_rows(staff_client, author):
    client = staff_client("change_author", "view_book", "delete_book")
    rows = list(Book.objects.filter(author=author).order_by("pk")[:10])
    data = {
        key: value
        for key, value in inline_data(author, "books", rows).items()
        if key.endswith(("-id", "-author", "_FORMS"))
    }
    data["books-2-DELETE"] = "on"
    response = client.post(save_url(author), data)

    assert b'data-status="saved"' in response.content
    assert not Book.objects.filter(pk=rows[2].pk).exists()
    assert Book.objects.filter(author=author).count() == 24


def test_no_save_button_without_the_admin_mixin(admin_user, author):
    from django.test import RequestFactory

    site = admin.AdminSite(name="unrouted_site")

    class BookInline(InlineControlsMixin, admin.TabularInline):
        model = Book
        inline_save_button = True

    request = RequestFactory().get("/")
    request.user = admin_user
    inline = BookInline(Author, site)
    formset = inline.get_formset(request, author)(instance=author, prefix="books")

    assert formset.inline_controls.save_url is None
    assert formset.inline_controls.has_footer is False


def test_check_requires_admin_mixin():
    site = admin.AdminSite(name="check_site")

    class BookInline(InlineControlsMixin, admin.TabularInline):
        model = Book
        inline_save_button = True

    @admin.register(Author, site=site)
    class AuthorAdmin(admin.ModelAdmin):
        inlines = [BookInline]

    ids = [error.id for error in BookInline(Author, site).check()]
    assert "admin_inline_controls.E008" in ids


def test_nested_rejects_save_button():
    nested_admin = pytest.importorskip("nested_admin")
    from django_admin_inline_controls.contrib.nested import NestedInlineControlsMixin

    class BookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
        model = Book
        inline_save_button = True

    ids = [error.id for error in BookInline(Author, admin.site).check()]
    assert "admin_inline_controls.E102" in ids
