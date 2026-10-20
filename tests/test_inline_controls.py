import datetime
import json

from demo.models import Article, Author, Book
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from unittest_parametrize import ParametrizedTestCase, parametrize

CHANGE_URL = "admin:demo_author_change"


def change_url(author, query=""):
    url = reverse(CHANGE_URL, args=[author.pk])
    return f"{url}?{query}" if query else url


def formset(response, prefix):
    for inline_admin_formset in response.context["inline_admin_formsets"]:
        if inline_admin_formset.formset.prefix == prefix:
            return inline_admin_formset.formset
    raise AssertionError(f"No formset with prefix {prefix!r}")


def titles(response, prefix="books"):
    return [form.instance.title for form in formset(response, prefix).initial_forms]


def pages(response, prefix="books"):
    return [form.instance.pages for form in formset(response, prefix).initial_forms]


def config(response, prefix="books"):
    return json.loads(formset(response, prefix).inline_controls.config_json)


def management_data(prefix, total, initial):
    return {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": str(initial),
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


def post_data(author, books=(), articles=()):
    data = {"name": author.name}
    data.update(management_data("books", len(books), len(books)))
    for index, book in enumerate(books):
        data.update(
            {
                f"books-{index}-id": str(book.pk),
                f"books-{index}-author": str(author.pk),
                f"books-{index}-title": book.title,
                f"books-{index}-status": book.status,
                f"books-{index}-published": book.published.isoformat()
                if book.published
                else "",
                f"books-{index}-pages": str(book.pages),
            }
        )
        if book.featured:
            data[f"books-{index}-featured"] = "on"
    data.update(management_data("articles", len(articles), len(articles)))
    for index, article in enumerate(articles):
        data.update(
            {
                f"articles-{index}-id": str(article.pk),
                f"articles-{index}-author": str(author.pk),
                f"articles-{index}-title": article.title,
                f"articles-{index}-words": str(article.words),
            }
        )
    data.update(management_data("books-2", 0, 0))
    return data


class TestPagination(ParametrizedTestCase, TestCase):
    """Paginating an inline."""

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

    def test_first_page_has_per_page_rows(self):
        response = self.client.get(change_url(self.author))

        assert response.status_code == 200
        assert titles(response) == [f"Book {n:02d}" for n in range(1, 11)]
        controls = formset(response, "books").inline_controls
        assert controls.total_count == 25
        assert [link.number for link in controls.page_links] == [1, 2, 3]
        assert controls.page_links[0].current

    def test_page_param_selects_page(self):
        response = self.client.get(change_url(self.author, "books-page=3"))

        assert titles(response) == [f"Book {n:02d}" for n in range(21, 26)]

    @parametrize(("page", "expected"), [("abc", "Book 01"), ("99", "Book 21")])
    def test_invalid_or_out_of_range_page(self, page, expected):
        response = self.client.get(change_url(self.author, f"books-page={page}"))

        assert titles(response)[0] == expected

    def test_page_links_keep_other_params(self):
        response = self.client.get(
            change_url(self.author, "books-o=-pages&articles-page=2")
        )
        link = formset(response, "books").inline_controls.page_links[1]

        assert link.url == "?books-o=-pages&articles-page=2&books-page=2"

    def test_inlines_on_the_same_page_are_independent(self):
        response = self.client.get(change_url(self.author, "books-page=2"))

        # "books-2" is the stacked inline of the same model: its own page 1.
        assert titles(response, "books")[0] == "Book 11"
        assert titles(response, "books-2")[0] == "Book 01"

    def test_add_view_renders_without_controls(self):
        response = self.client.get(reverse("admin:demo_author_add"))

        assert response.status_code == 200
        assert formset(response, "books").inline_controls is None
        assert b"data-inline-controls" not in response.content

    def test_plain_inline_renders_like_a_normal_inline(self):
        url = reverse("test_admin:demo_author_change", args=[self.author.pk])
        response = self.client.get(url)
        plain = formset(response, "books-2")

        assert len(plain.initial_forms) == 25
        assert plain.inline_controls.paginator is None
        html = response.content.decode()
        start = html.index('id="books-2-inline-controls"')
        plain_html = html[start : html.index('id="books-3-inline-controls"')]
        assert "inline-controls-toolbar" not in plain_html
        assert "inline-controls-footer" not in plain_html


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


class TestFilters(ParametrizedTestCase, TestCase):
    """Filtering an inline."""

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

    @parametrize(
        ("query", "expected_count"),
        [
            ("books-f-status=published", 13),
            ("books-f-title__icontains=book 1", 10),
            ("books-f-featured=true", 5),
            ("books-f-featured=false", 20),
            ("books-f-published__gte=2020-01-20", 7),
            ("books-f-status=published&books-f-featured=true", 3),
        ],
    )
    def test_filters(self, query, expected_count):
        response = self.client.get(change_url(self.author, query))

        assert formset(response, "books").inline_controls.total_count == expected_count

    def test_invalid_filter_value_is_ignored_and_reported(self):
        response = self.client.get(
            change_url(self.author, "books-f-published__gte=nope")
        )
        controls = formset(response, "books").inline_controls

        assert controls.total_count == 25
        assert "published__gte" in controls.filter_form.errors

    def test_filter_widgets_are_detached_from_the_change_form(self):
        response = self.client.get(change_url(self.author))

        assert b'form="books-inline-controls-filters"' in response.content
        assert config(response)["filterParams"] == [
            "books-f-title__icontains",
            "books-f-status",
            "books-f-publisher",
            "books-f-featured",
            "books-f-published__gte",
        ]

    def test_filtering_resets_pagination_in_links(self):
        response = self.client.get(change_url(self.author, "books-f-status=draft"))

        assert formset(response, "books").inline_controls.is_filtered
        assert b"data-inline-controls-clear" in response.content

    def test_custom_filter_form(self):
        url = reverse("test_admin:demo_author_change", args=[self.author.pk])
        response = self.client.get(f"{url}?books-f-q=book 2&books-f-status=published")

        assert titles(response) == ["Book 21", "Book 23", "Book 25"]


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


class TestInfiniteMode(TestCase):
    """Infinite pagination."""

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

    def test_infinite_mode_config(self):
        response = self.client.get(change_url(self.author))
        data = config(response, "articles")

        assert data["mode"] == "infinite"
        assert data["loadedCount"] == 15
        assert data["totalCount"] == 20
        assert data["nextUrl"] == "?articles-page=2"
        assert b"data-inline-controls-more" in response.content

    def test_infinite_mode_last_page_has_no_next(self):
        response = self.client.get(change_url(self.author, "articles-page=2"))

        assert config(response, "articles")["nextUrl"] is None
        assert len(formset(response, "articles").initial_forms) == 5
