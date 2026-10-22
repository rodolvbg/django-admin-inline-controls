"""What the tests of the inline controls share: the demo's change page."""

import json

from django.urls import reverse

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
