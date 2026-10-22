"""The contrib mixins: edge cases."""

import datetime

import pytest
from demo.models import Article, Author, Book
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase


def get_request(user, data=None, method="get"):
    request = getattr(RequestFactory(), method)("/", data or {})
    request.user = user
    return request


def build_formset(inline, request, author, **kwargs):
    return inline.get_formset(request, author)(
        instance=author, prefix="books", **kwargs
    )


class TestContribEdgeCases(TestCase):
    """Contrib mixins' remaining branches."""

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

    def test_filterset_kwargs_default_to_empty(self):
        django_filters = pytest.importorskip("django_filters")
        from django_admin_inline_controls.contrib.filters import (
            FilterSetInlineControlsMixin,
        )

        class BookFilterSet(django_filters.FilterSet):
            class Meta:
                model = Book
                fields = ["status"]

        class BookInline(FilterSetInlineControlsMixin, admin.TabularInline):
            model = Book
            inline_filterset_class = BookFilterSet

        inline = BookInline(Author, admin.site)
        formset = build_formset(
            inline, get_request(self.user, {"books-f-status": "draft"}), self.author
        )

        assert inline.get_inline_filterset_kwargs(None, self.author) == {}
        assert formset.get_queryset().count() == 12

    def test_nested_mixin_pages_mode_passes_checks(self):
        nested_admin = pytest.importorskip("nested_admin")
        from django_admin_inline_controls.contrib.nested import (
            NestedInlineControlsMixin,
        )

        class BookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
            model = Book
            inline_per_page = 5

        assert BookInline(Author, admin.site).check() == []
