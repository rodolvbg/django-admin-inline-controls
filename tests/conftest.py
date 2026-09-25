import datetime
import os

import pytest
from demo.models import Article, Author, Book
from django.contrib.auth.models import User

# pytest-playwright's sync API runs its driver via a greenlet-based
# bridge to an asyncio event loop in a background thread. That's enough
# for Django's asyncio-safety check to (falsely) think DB access is
# happening from an async context once `live_server`/Playwright fixtures
# are involved, even though nothing here is actually concurrent. This is
# the documented escape hatch for that exact combination.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("admin", "admin@example.com", "password")


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def author(db):
    """An author with 25 books (pages = 10 * n) and 20 articles."""
    author = Author.objects.create(name="Author")
    statuses = [Book.Status.DRAFT, Book.Status.PUBLISHED]
    Book.objects.bulk_create(
        Book(
            author=author,
            title=f"Book {n:02d}",
            status=statuses[n % 2],
            published=datetime.date(2020, 1, 1) + datetime.timedelta(days=n),
            pages=10 * n,
            featured=n % 5 == 0,
        )
        for n in range(1, 26)
    )
    Article.objects.bulk_create(
        Article(author=author, title=f"Article {n:02d}", words=n) for n in range(1, 21)
    )
    return author


@pytest.fixture
def other_author(db):
    author = Author.objects.create(name="Other")
    Book.objects.create(author=author, title="Other book", pages=1)
    return author
