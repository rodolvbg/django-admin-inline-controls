from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Book(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        OUT_OF_PRINT = "out_of_print", "Out of print"

    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="books")
    title = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    published = models.DateField(null=True, blank=True)
    pages = models.PositiveIntegerField(default=0)
    featured = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class Article(models.Model):
    author = models.ForeignKey(
        Author, on_delete=models.CASCADE, related_name="articles"
    )
    title = models.CharField(max_length=200)
    words = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.title
