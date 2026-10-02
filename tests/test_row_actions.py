import pytest
from demo.models import Author, Book
from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.http import HttpResponse
from django.urls import reverse

from django_admin_inline_controls.actions import inline_action
from django_admin_inline_controls.mixins import InlineControlsMixin
from django_admin_inline_controls.row_actions import (
    get_render_context,
    row_action_spec,
    run_row_action,
    takes_one_row,
)
from tests.test_actions import action_url, staff_client  # noqa: F401
from tests.test_inline_controls import change_url, config


def row_run(client, author, name, pk, **extra):
    data = {"row_action": name, "_selected_action": str(pk), **extra}
    return client.post(action_url(author), data)


def status(response):
    content = response.content.decode()
    return content.split('data-status="')[1].split('"')[0]


def message(response):
    content = response.content.decode()
    return content.split('data-message="')[1].split('"')[0]


def first_book(author):
    # The demo inline's first page: Book 01…Book 10.
    return Book.objects.get(author=author, title="Book 01")


# Rendering ----------------------------------------------------------------------


def test_row_actions_column_is_rendered(admin_client, author):
    response = admin_client.get(change_url(author))
    html = response.content.decode()
    book = first_book(author)

    assert 'class="column-inline_controls_row_actions' in html
    # Hidden until the JS shows them; one set per saved row on the page.
    assert html.count("data-inline-controls-row-actions hidden") == 10
    view_url = reverse("admin:demo_book_change", args=[book.pk])
    assert f'href="{view_url}" role="button"' in html
    assert (
        f'data-inline-controls-row-action="toggle_featured" data-pk="{book.pk}"'
    ) in html
    assert ">Feature</button>" in html
    assert 'data-confirmation="Delete “Book 01”? This cannot be undone."' in html
    data = config(response)
    assert data["rowActions"] is True
    assert data["actionUrl"] == action_url(author)


def test_feature_label_follows_the_row(admin_client, author):
    Book.objects.filter(title="Book 01").update(featured=True)
    html = admin_client.get(change_url(author)).content.decode()

    assert ">Unfeature</button>" in html


def test_no_row_actions_in_the_add_view(admin_client, db):
    html = admin_client.get(reverse("admin:demo_author_add")).content.decode()

    assert "inline_controls_row_actions" not in html
    assert "data-inline-controls-row-action" not in html


def test_row_actions_are_filtered_by_permission(staff_client, author):  # noqa: F811
    client = staff_client("view_author", "view_book", "change_book")
    html = client.get(change_url(author)).content.decode()

    assert 'data-inline-controls-row-action="toggle_featured"' in html
    assert 'data-inline-controls-row-action="delete"' not in html


# Running ------------------------------------------------------------------------


def test_one_row_action(admin_client, author):
    book = first_book(author)
    response = row_run(admin_client, author, "toggle_featured", book.pk)

    assert response.status_code == 200
    assert status(response) == "done"
    assert message(response) == "“Book 01” is featured."
    book.refresh_from_db()
    assert book.featured
    assert b'id="books-inline-controls"' in response.content


def test_delete_row_action(admin_client, author):
    book = first_book(author)
    response = row_run(admin_client, author, "delete", book.pk)

    assert status(response) == "done"
    assert not Book.objects.filter(pk=book.pk).exists()
    entry = LogEntry.objects.get()
    assert entry.object_id == str(author.pk)
    assert entry.get_change_message() == "Deleted book “Book 01”."


def test_view_row_action_redirects(admin_client, author):
    book = first_book(author)
    response = row_run(admin_client, author, "view", book.pk)

    assert response.status_code == 302
    assert response["Location"] == reverse("admin:demo_book_change", args=[book.pk])


def test_forbidden_or_unknown_row_actions(staff_client, author, other_author):  # noqa: F811
    book = first_book(author)
    client = staff_client("view_author", "view_book", "change_book")

    assert row_run(client, author, "delete", book.pk).status_code == 400
    assert Book.objects.filter(pk=book.pk).exists()
    assert row_run(client, author, "nope", book.pk).status_code == 400
    # Another parent's row, or no valid row at all.
    other = Book.objects.get(author=other_author)
    assert row_run(client, author, "toggle_featured", other.pk).status_code == 400
    assert row_run(client, author, "toggle_featured", "x").status_code == 400


# Specs and hooks ----------------------------------------------------------------


def make_inline(site=admin.site, **attrs):
    inline_class = type(
        "BookInline",
        (InlineControlsMixin, admin.TabularInline),
        {"model": Book, "__module__": __name__, **attrs},
    )
    return inline_class(Author, site)


def one_row(self, request, obj, parent_obj=None):
    self.message_user(request, f"one {obj} of {parent_obj}", messages.INFO)


one_row.short_description = "One %(verbose_name)s"
one_row.css_classes = "danger"
one_row.attribute_properties = {"title": 'say "hi"'}


@inline_action(description="On %(verbose_name_plural)s", confirmation="Sure?")
def on_queryset(inline, request, queryset):
    return HttpResponse(f"{queryset.count()} {queryset.get()}")


def test_row_action_specs_and_hooks(admin_user, rf, author):
    def get_on_queryset_label(self, obj):
        return f"Label {obj}"

    def get_on_queryset_css(self, obj):
        return "hooked"

    def get_on_queryset_attr(self, obj):
        return 'data-x="1"'

    inline = make_inline(
        inline_row_actions=[one_row, "on_queryset"],
        on_queryset=on_queryset,
        get_on_queryset_label=get_on_queryset_label,
        get_on_queryset_css=get_on_queryset_css,
        get_on_queryset_attr=get_on_queryset_attr,
    )
    book = first_book(author)
    request = rf.get("/")
    request.user = admin_user

    specs = inline.get_inline_row_action_specs(request, author, book)
    first, second = specs["one_row"], specs["on_queryset"]
    assert (first.label, first.css_classes, str(first.attrs)) == (
        "One book",
        "danger",
        'title="say &quot;hi&quot;"',
    )
    assert first.confirmation is None and first.url is None
    assert (second.label, second.css_classes, str(second.attrs)) == (
        "Label Book 01",
        "hooked",
        'data-x="1"',
    )
    assert second.confirmation == "Sure?"
    assert inline.get_inline_row_action_specs(request, author, None) == {}
    assert inline.get_inline_row_action_specs(None, author, book) == {}

    # Each runs in the form it was written for.
    assert takes_one_row(one_row) and not takes_one_row(on_queryset)
    assert run_row_action(inline, request, second, book, author).content == (
        b"1 Book 01"
    )


def test_default_label_and_view_without_a_change_view(admin_user, rf, author):
    site = admin.AdminSite(name="no_book_site")

    def publish_it(self, request, obj, parent_obj=None):
        return None

    inline = make_inline(
        site, inline_row_actions=["view", "publish_it"], publish_it=publish_it
    )
    request = rf.get("/")
    request.user = admin_user
    specs = inline.get_inline_row_action_specs(request, author, first_book(author))

    # Book has no change view on this site: no "view".
    assert list(specs) == ["publish_it"]
    assert specs["publish_it"].label == "Publish it"
    spec = row_action_spec(inline, "publish_it", publish_it, first_book(author))
    assert str(spec.attrs) == ""


def test_column_without_render_context(author):
    inline = make_inline(inline_row_actions=["view"])

    assert get_render_context(inline) == (None, None)
    assert inline.inline_controls_row_actions(first_book(author)) == ""


def test_column_is_added_to_fieldsets(admin_user, rf, author):
    inline = make_inline(
        inline_row_actions=["view"], fieldsets=[(None, {"fields": ["title"]})]
    )
    request = rf.get("/")
    request.user = admin_user

    assert inline.get_fieldsets(request, author) == [
        (None, {"fields": ["title", "inline_controls_row_actions"]})
    ]
    assert inline.get_fieldsets(request, None) == [(None, {"fields": ["title"]})]
    assert "inline_controls_row_actions" in inline.get_readonly_fields(request, author)
    assert "inline_controls_row_actions" not in inline.get_readonly_fields(request)
    # Not twice, when the column is listed already.
    listed = make_inline(
        inline_row_actions=["view"],
        fields=["title", "inline_controls_row_actions"],
        readonly_fields=["inline_controls_row_actions"],
    )
    assert listed.get_fields(request, author).count("inline_controls_row_actions") == 1
    assert (
        listed.get_readonly_fields(request, author).count("inline_controls_row_actions")
        == 1
    )


def test_row_actions_load_the_actions_script():
    media = str(make_inline(inline_row_actions=["view"]).media)

    assert "django_admin_inline_controls/js/actions.js" in media


# Checks ---------------------------------------------------------------------------


def test_check_unknown_row_action():
    ids = [e.id for e in make_inline(inline_row_actions=["nope", 3]).check()]

    assert ids.count("admin_inline_controls.E018") == 2


def test_check_row_actions_require_admin_mixin():
    site = admin.AdminSite(name="row_actions_check_site")
    inline = make_inline(site, inline_row_actions=["view"])

    @admin.register(Author, site=site)
    class AuthorAdmin(admin.ModelAdmin):
        inlines = [type(inline)]

    assert "admin_inline_controls.E019" in [e.id for e in inline.check()]


def test_nested_rejects_row_actions():
    nested_admin = pytest.importorskip("nested_admin")
    from django_admin_inline_controls.contrib.nested import NestedInlineControlsMixin

    class BookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
        model = Book
        inline_row_actions = ["view"]

    ids = [e.id for e in BookInline(Author, admin.site).check()]
    assert "admin_inline_controls.E105" in ids
