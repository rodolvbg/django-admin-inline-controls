import datetime
import importlib
import sys

import pytest
from demo.models import Article, Author, Book
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase
from unittest_parametrize import ParametrizedTestCase, parametrize


@pytest.fixture
def get_request(admin_user):
    def make(data=None):
        request = RequestFactory().get("/", data or {})
        request.user = admin_user
        return request

    return make


@pytest.fixture
def filterset_inline():
    django_filters = pytest.importorskip("django_filters")
    from django_admin_inline_controls.contrib.filters import (
        FilterSetInlineControlsMixin,
    )

    class BookFilterSet(django_filters.FilterSet):
        min_pages = django_filters.NumberFilter(field_name="pages", lookup_expr="gte")

        class Meta:
            model = Book
            fields = ["status"]

        def __init__(self, *args, parent=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.parent = parent

    class BookInline(FilterSetInlineControlsMixin, admin.TabularInline):
        model = Book
        inline_per_page = 5
        inline_filterset_class = BookFilterSet

        def get_inline_filterset_kwargs(self, request, obj):
            return {"parent": obj}

    return BookInline(Author, admin.site)


@pytest.fixture
def unfold_mixin():
    pytest.importorskip("unfold")
    from django_admin_inline_controls.contrib.unfold import UnfoldInlineControlsMixin

    return UnfoldInlineControlsMixin


def unfold_inline(mixin, **attrs):
    inline_class = type(
        "BookInline", (mixin, admin.TabularInline), {"model": Book, **attrs}
    )
    return inline_class(Author, admin.AdminSite(name="unfold_site"))


class TestContribImports(ParametrizedTestCase, SimpleTestCase):
    """Importing contrib modules."""

    @parametrize(
        ("module", "dependency", "extra"),
        [
            (
                "django_admin_inline_controls.contrib.filters",
                "django_filters",
                "filters",
            ),
            ("django_admin_inline_controls.contrib.nested", "nested_admin", "nested"),
            ("django_admin_inline_controls.contrib.unfold", "unfold", "unfold"),
        ],
    )
    def test_contrib_import_without_extra_raises_helpful_error(
        self, monkeypatch, module, dependency, extra
    ):
        monkeypatch.setitem(sys.modules, dependency, None)
        monkeypatch.delitem(sys.modules, module, raising=False)

        with pytest.raises(
            ImportError, match=rf"django-admin-inline-controls\[{extra}\]"
        ):
            importlib.import_module(module)


class TestFilterSetInlineControlsMixin(TestCase):
    """The django-filter integration."""

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

    def test_filterset_filters_the_inline(self, filterset_inline, get_request):
        request = get_request(
            {"books-f-status": "published", "books-f-min_pages": "200"}
        )
        formset_class = filterset_inline.get_formset(request, self.author)
        formset = formset_class(instance=self.author, prefix="books")

        assert [b.pages for b in formset.get_queryset()] == [210, 230, 250]
        controls = formset.inline_controls
        assert controls.total_count == 3
        assert controls.filter_param_names == ["books-f-status", "books-f-min_pages"]
        assert controls.filter_form.fields["status"].widget.attrs["form"] == (
            "books-inline-controls-filters"
        )

    def test_filterset_receives_parent_and_request(self, filterset_inline, get_request):
        request = get_request()
        captured = {}
        filterset_class = filterset_inline.inline_filterset_class
        original_init = filterset_class.__init__

        def spy(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            captured.update(parent=self.parent, request=self.request)

        filterset_class.__init__ = spy
        try:
            filterset_inline.get_formset(request, self.author)(
                instance=self.author, prefix="books"
            ).get_queryset()
        finally:
            filterset_class.__init__ = original_init

        assert captured == {"parent": self.author, "request": request}

    def test_filterset_mixin_without_filterset_falls_back_to_fields(self, get_request):
        pytest.importorskip("django_filters")
        from django_admin_inline_controls.contrib.filters import (
            FilterSetInlineControlsMixin,
        )

        class BookInline(FilterSetInlineControlsMixin, admin.TabularInline):
            model = Book
            inline_filter_fields = ["status"]

        request = get_request({"books-f-status": "draft"})
        formset = BookInline(Author, admin.site).get_formset(request, self.author)(
            instance=self.author, prefix="books"
        )

        assert formset.get_queryset().count() == 12


class TestNestedInlineControlsMixin(TestCase):
    """The django-nested-admin integration."""

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

    def test_nested_mixin_disables_ajax_and_infinite(self):
        pytest.importorskip("nested_admin")
        import nested_admin

        from django_admin_inline_controls.contrib.nested import (
            NestedInlineControlsMixin,
        )

        class BookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
            model = Book
            inline_per_page = 5
            inline_pagination = "infinite"

        inline = BookInline(Author, admin.site)

        assert inline.inline_controls_ajax is False
        assert "admin_inline_controls.E101" in [e.id for e in inline.check()]

    def test_nested_mixin_renders_in_nested_admin(self):
        pytest.importorskip("nested_admin")
        response = self.client.get(
            f"/test-admin/nested/demo/author/{self.author.pk}/change/"
        )

        assert response.status_code == 200
        assert b'id="books-inline-controls"' in response.content
        assert b"&quot;ajax&quot;: false" in response.content


class TestUnfoldInlineControlsMixin(TestCase):
    """The django-unfold integration."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )

    def test_unfold_selectors_under_the_inline_own(self, unfold_mixin, get_request):
        from django_admin_inline_controls.contrib.unfold import UNFOLD_SELECTORS
        from django_admin_inline_controls.controls import DEFAULT_SELECTORS

        inline = unfold_inline(
            unfold_mixin, inline_controls_selectors={"row_label": ".mine"}
        )
        selectors = inline.get_inline_controls_selectors(get_request(), None)

        assert selectors["form_rows"] == UNFOLD_SELECTORS["form_rows"]
        assert selectors["saved_row"] == [".original"]
        assert selectors["row_label"] == [".mine"]
        assert selectors["heading"] == DEFAULT_SELECTORS["heading"]

    def test_unfold_media(self, unfold_mixin):
        media = str(
            unfold_inline(unfold_mixin, inline_bulk_actions=["delete_selected"]).media
        )

        for path in ["js/core.js", "js/actions.js", "js/contrib/unfold.js"]:
            assert f"django_admin_inline_controls/{path}" in media
        assert "css/core.css" in media
        assert "css/contrib/unfold.css" in media

    def test_unfold_per_page_is_an_error(self, unfold_mixin):
        ids = lambda inline: [error.id for error in inline.check()]  # noqa: E731

        assert "admin_inline_controls.E104" in ids(
            unfold_inline(unfold_mixin, per_page=10)
        )
        assert "admin_inline_controls.E104" not in ids(unfold_inline(unfold_mixin))
