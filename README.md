# django-admin-inline-controls

[![Build status](https://github.com/rodolvbg/django-admin-inline-controls/actions/workflows/pytest.yml/badge.svg)](https://github.com/rodolvbg/django-admin-inline-controls/actions/workflows/pytest.yml)
[![PyPI version](https://img.shields.io/pypi/v/django-admin-inline-controls.svg)](https://pypi.org/project/django-admin-inline-controls/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-admin-inline-controls)](https://pypi.org/project/django-admin-inline-controls/)
[![PyPI - Django Version](https://img.shields.io/pypi/djversions/django-admin-inline-controls)](https://pypi.org/project/django-admin-inline-controls/)
[![Downloads](https://static.pepy.tech/personalized-badge/django-admin-inline-controls?period=month&units=international_system&left_color=black&right_color=blue&left_text=Downloads/month)](https://pepy.tech/project/django-admin-inline-controls)

Pagination, filtering and sortable columns for Django admin inlines —
without leaving the change form.

![A paginated, filtered and sorted tabular inline](docs/screenshots/hero.png)

- **Pagination**: page links, or infinite scroll that appends rows as you
  reach the end of the inline.
- **Filters**: generated from lookups (`"status"`, `"title__icontains"`,
  `"published__gte"`), your own `forms.Form`, or a django-filter `FilterSet`.
- **Sortable columns**: click a tabular header (or the toolbar links on
  stacked inlines); multi-column, like the changelist.
- Filters, sorting and page links refresh **only that inline** in place.
  Several controlled inlines on the same page keep independent state.
- Rows loaded from several pages are saved together, and unsaved edits are
  never silently thrown away.
- Only depends on Django. No jQuery plugins, no htmx; works with
  `TabularInline` and `StackedInline`.

## Install

```bash
pip install django-admin-inline-controls
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "django_admin_inline_controls",
]
```

## Usage

Mix `InlineControlsMixin` in before `TabularInline` or `StackedInline`:

```python
from django.contrib import admin
from django.db.models.functions import Lower

from django_admin_inline_controls.mixins import InlineControlsMixin


class BookInline(InlineControlsMixin, admin.TabularInline):
    model = Book
    extra = 0
    inline_per_page = 20
    inline_ordering_fields = {
        "title": Lower("title"),  # column name -> ordering expression
        "published": "published",
        "pages": "pages",
    }
    inline_filter_fields = ["title__icontains", "status", "featured", "published__gte"]


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    inlines = [BookInline]
```

State lives in the URL, namespaced by the formset prefix
(`?books-page=2&books-o=-pages&books-f-status=published`), so links are
shareable and several inlines never clash.

### Options

| Attribute | Default | |
|---|---|---|
| `inline_per_page` | `None` | Rows per page. `None` disables pagination. |
| `inline_pagination` | `"pages"` | `"pages"` or `"infinite"` (load more on scroll). |
| `inline_ordering_fields` | `()` | Sortable columns: a list of field names, or `{column: expression}`. The expression can be a field path, an ORM expression (`Lower("title")`, `F("date").asc(nulls_last=True)`) or an explicit `(ascending, descending)` pair. |
| `inline_default_ordering` | `()` | Applied after the user's ordering. Defaults to the queryset's / model's ordering; `pk` is always appended so pages are stable. |
| `inline_filter_fields` | `()` | Filter lookups. A form is generated from them. |
| `inline_filter_form` | `None` | Your own filter `forms.Form`. |
| `inline_controls_ajax` | `True` | Refresh the inline in place instead of reloading the page. |

Only columns declared in `inline_ordering_fields` can be sorted: ordering
by an arbitrary field from the URL would let anyone infer the values of
fields the inline never shows.

### Custom filters

Generated fields depend on the model field and lookup (choices → select,
`BooleanField` → Yes/No/any, dates → date input, relations →
`ModelChoiceField`, `__in` → multiple select, `__isnull` → Yes/No/any…).
Override `get_inline_filter_formfield(lookup)` to change one, or bring
your own form and handle the fields that aren't plain lookups:

```python
class BookFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search")
    status = forms.ChoiceField(required=False, choices=[("", "---"), *Book.Status.choices])


class BookInline(InlineControlsMixin, admin.TabularInline):
    model = Book
    inline_per_page = 20
    inline_filter_form = BookFilterForm
    inline_filter_fields = ["status"]  # applied as lookups; "q" is handled below

    def filter_inline_queryset(self, request, queryset, filters):
        if search := filters.get("q"):
            queryset = queryset.filter(Q(title__icontains=search) | Q(isbn=search))
        return super().filter_inline_queryset(request, queryset, filters)
```

Every option also has a `get_*` hook taking `(request, obj)` —
`get_inline_per_page`, `get_inline_ordering_fields`,
`get_inline_filter_fields`, `get_inline_filter_form_class`,
`get_inline_filter_form_kwargs` (e.g. to pass the parent object to your
form) — and `get_inline_filtered_queryset()` is the single seam to plug in
any other filtering backend.

### Infinite scroll

```python
class ArticleInline(InlineControlsMixin, admin.TabularInline):
    model = Article
    inline_per_page = 30
    inline_pagination = "infinite"
```

The next page is appended when the "Load more" link scrolls into view (or
is clicked). Loaded rows join the formset, so everything visible is saved
with the object. Keep in mind Django's formset limits: by default a
formset accepts at most 1000 forms per submission (`max_num`).

## Optional extras

The core only depends on Django. Integrations with third-party packages are
opt-in.

### django-filter

```bash
pip install django-admin-inline-controls[filters]
```

```python
from django_admin_inline_controls.contrib.filters import FilterSetInlineControlsMixin


class BookInline(FilterSetInlineControlsMixin, admin.TabularInline):
    model = Book
    inline_per_page = 20
    inline_filterset_class = BookFilterSet

    def get_inline_filterset_kwargs(self, request, obj):
        return {"parent": obj}  # extra kwargs for your FilterSet's __init__
```

The filterset gets the request too (`self.request`).

### django-nested-admin

```bash
pip install django-admin-inline-controls[nested]
```

```python
import nested_admin
from django_admin_inline_controls.contrib.nested import NestedInlineControlsMixin


class BookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
    model = Book
    inline_per_page = 20
```

nested_admin keeps its own client-side formset state, so with it filters,
sorting and page links reload the page instead of swapping the inline, and
infinite scroll is not available.

## JavaScript events

After an inline is refreshed in place, or rows are appended, an
`inline-controls:updated` event bubbles from the new content: hook your own
widget initialization there. The admin's own inline machinery, autocomplete,
date/time shortcuts and `filter_horizontal` widgets are re-initialized
automatically.

## Demo

```bash
cd example
python manage.py migrate
python manage.py seed_demo      # admin/admin + an author with many books
python manage.py runserver
```

## Compatibility

Django 4.2 – 6.1, Python 3.10+.

## License

MIT
