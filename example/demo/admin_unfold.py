"""The demo's admin on an Unfold site (see ``example.settings_unfold``)."""

from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.sites import UnfoldAdminSite

from django_admin_inline_controls.contrib.unfold import UnfoldInlineControlsMixin

from . import admin as demo
from .models import Author, Book

site = UnfoldAdminSite(name="admin")


class BookInline(UnfoldInlineControlsMixin, demo.BookInline, TabularInline):
    pass


class ArticleInline(UnfoldInlineControlsMixin, demo.ArticleInline, TabularInline):
    tab = True


class BookStackedInline(
    UnfoldInlineControlsMixin, demo.BookStackedInline, StackedInline
):
    # Unfold collapses the stacked rows itself.
    classes = []
    collapsible = True


class AuthorAdmin(demo.AuthorAdmin, ModelAdmin):
    inlines = [BookInline, ArticleInline, BookStackedInline]


class BookAdmin(demo.BookAdmin, ModelAdmin):
    pass


site.register(Author, AuthorAdmin)
site.register(Book, BookAdmin)
