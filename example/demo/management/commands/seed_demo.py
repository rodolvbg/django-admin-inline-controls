import datetime
import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from demo.models import Article, Author, Book

WORDS = "red blue green night river stone glass winter garden silent iron paper".split()


class Command(BaseCommand):
    help = "Create an admin/admin superuser and an author with many books and articles."

    def handle(self, *args, **options):
        random.seed(42)
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin")
        author, _ = Author.objects.get_or_create(name="Demo Author")
        author.books.all().delete()
        author.articles.all().delete()
        Book.objects.bulk_create(
            Book(
                author=author,
                title=f"{' '.join(random.sample(WORDS, 2)).title()} {index}",
                status=random.choice(Book.Status.values),
                published=datetime.date(2000, 1, 1)
                + datetime.timedelta(days=random.randint(0, 9000)),
                pages=random.randint(80, 900),
                featured=random.random() < 0.2,
            )
            for index in range(1, 96)
        )
        Article.objects.bulk_create(
            Article(
                author=author,
                title=f"Article {index}: {random.choice(WORDS)}",
                words=random.randint(300, 5000),
            )
            for index in range(1, 71)
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {author} (pk={author.pk}). Log in as admin/admin."
            )
        )
