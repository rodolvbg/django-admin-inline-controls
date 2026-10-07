import csv

from django.contrib import admin, messages
from django.db.models import Avg, Count, Sum
from django.db.models.functions import Lower
from django.http import HttpResponse

from django_admin_inline_controls.actions import DefaultActionsMixin, inline_action
from django_admin_inline_controls.mixins import (
    InlineControlsAdminMixin,
    InlineControlsMixin,
)

from .models import Article, Author, Book, Publisher


class BookInline(DefaultActionsMixin, InlineControlsMixin, admin.TabularInline):
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
        "publisher",
        "featured",
        "published__gte",
    ]
    # The publisher filter searches as you type; the status one only offers
    # the statuses this author's books have.
    inline_filter_autocomplete = ["publisher"]
    inline_filter_only_used_values = True
    inline_save_button = True
    inline_bulk_actions = ["mark_published", "export_csv", "delete_selected"]
    # Row actions, as in django-inline-actions: View and Delete come from
    # DefaultActionsMixin.
    inline_actions = ["toggle_featured"]
    inline_footer_rows = [
        ("Total", {"title": Count("pk"), "pages": Sum("pages")}),
        ("Average", {"pages": Avg("pages")}),
    ]

    @inline_action(
        permissions=["change"],
        description="Mark selected %(verbose_name_plural)s as published",
    )
    def mark_published(self, request, queryset):
        count = queryset.update(status=Book.Status.PUBLISHED)
        self.message_user(request, f"{count} books published.", messages.SUCCESS)

    def toggle_featured(self, request, obj, parent_obj=None):
        """A row action with django-inline-actions' signature."""
        obj.featured = not obj.featured
        obj.save(update_fields=["featured"])
        state = "featured" if obj.featured else "no longer featured"
        self.message_user(request, f"“{obj}” is {state}.", messages.SUCCESS)

    def get_toggle_featured_label(self, obj):
        return "Unfeature" if obj.featured else "Feature"

    @inline_action(description="Export selected %(verbose_name_plural)s to CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="books.csv"'
        writer = csv.writer(response)
        writer.writerow(["title", "status", "published", "pages"])
        for book in queryset:
            writer.writerow([book.title, book.status, book.published, book.pages])
        return response


class ArticleInline(InlineControlsMixin, admin.TabularInline):
    model = Article
    extra = 0
    fields = ["title", "words"]
    inline_per_page = 15
    inline_pagination = "infinite"
    inline_ordering_fields = ["title", "words"]
    inline_save_button = True
    inline_bulk_actions = ["delete_selected"]
    inline_footer_rows = [("Total", {"words": Sum("words")})]


class BookStackedInline(InlineControlsMixin, admin.StackedInline):
    model = Book
    extra = 0
    fields = ["title", "status", "pages"]
    verbose_name_plural = "Books (stacked)"
    inline_per_page = 3
    inline_ordering_fields = ["title", "pages"]
    inline_filter_fields = ["status"]
    inline_footer_rows = [("Total", {"pages": Sum("pages")})]
    classes = ["collapse"]


@admin.register(Author)
class AuthorAdmin(InlineControlsAdminMixin, admin.ModelAdmin):
    list_display = ["name"]
    inlines = [BookInline, ArticleInline, BookStackedInline]


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "status", "published"]


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    search_fields = ["name"]
