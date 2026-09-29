from django.contrib import admin
from django.db.models.functions import Lower

from django_admin_inline_controls.mixins import (
    InlineControlsAdminMixin,
    InlineControlsMixin,
)

from .models import Article, Author, Book


class BookInline(InlineControlsMixin, admin.TabularInline):
    model = Book
    extra = 0
    fields = ["title", "status", "published", "pages", "featured"]
    inline_per_page = 10
    inline_ordering_fields = {
        "title": Lower("title"),
        "published": "published",
        "pages": "pages",
    }
    inline_filter_fields = [
        "title__icontains",
        "status",
        "featured",
        "published__gte",
    ]
    inline_save_button = True


class ArticleInline(InlineControlsMixin, admin.TabularInline):
    model = Article
    extra = 0
    fields = ["title", "words"]
    inline_per_page = 15
    inline_pagination = "infinite"
    inline_ordering_fields = ["title", "words"]
    inline_save_button = True


class BookStackedInline(InlineControlsMixin, admin.StackedInline):
    model = Book
    extra = 0
    fields = ["title", "status", "pages"]
    verbose_name_plural = "Books (stacked)"
    inline_per_page = 3
    inline_ordering_fields = ["title", "pages"]
    inline_filter_fields = ["status"]
    classes = ["collapse"]


@admin.register(Author)
class AuthorAdmin(InlineControlsAdminMixin, admin.ModelAdmin):
    list_display = ["name"]
    inlines = [BookInline, ArticleInline, BookStackedInline]


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "status", "published"]
