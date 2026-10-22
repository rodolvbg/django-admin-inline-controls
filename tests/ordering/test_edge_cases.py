"""InlineOrderingMixin: edge cases."""

import datetime

from demo.models import Article, Author, Book
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from unittest_parametrize import ParametrizedTestCase, parametrize

from django_admin_inline_controls.mixins import InlineControlsMixin


def get_request(user, data=None, method="get"):
    request = getattr(RequestFactory(), method)("/", data or {})
    request.user = user
    return request


def make_inline(**attrs):
    inline_class = type(
        "BookInline",
        (InlineControlsMixin, admin.TabularInline),
        {"model": Book, "__module__": __name__, **attrs},
    )
    return inline_class(Author, admin.site)


def build_formset(inline, request, author, **kwargs):
    return inline.get_formset(request, author)(
        instance=author, prefix="books", **kwargs
    )


class TestOrderBy(ParametrizedTestCase, TestCase):
    """Ordering of the inline queryset."""

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

    def test_explicit_pk_ordering_is_not_duplicated(self):
        inline = make_inline(inline_per_page=5, inline_default_ordering=["-pk"])
        formset = build_formset(inline, get_request(self.user), self.author)

        order_by = formset.inline_controls._order_by(Book.objects.all())

        assert order_by == ["-pk"]
        assert formset.get_queryset()[0].title == "Book 25"

    @parametrize(
        ("default_ordering", "expected"),
        [
            ((), ["title", "pk"]),
            (["-id"], ["title", "-id"]),
            (["pages"], ["title", "pages", "pk"]),
        ],
    )
    def test_pk_tie_breaker(self, default_ordering, expected):
        inline = make_inline(
            inline_ordering_fields=["title"], inline_default_ordering=default_ordering
        )
        formset = build_formset(
            inline, get_request(self.user, {"books-o": "title"}), self.author
        )

        assert formset.inline_controls._order_by(Book.objects.all()) == expected

    def test_ordering_column_without_field_uses_its_name(self):
        inline = make_inline(inline_ordering_fields={"custom": "pages"})
        formset = build_formset(
            inline, get_request(self.user, {"books-o": "-custom"}), self.author
        )
        formset.get_queryset()

        (column,) = formset.inline_controls.ordering_columns
        assert column.label == "custom"
        assert column.direction == "descending"
