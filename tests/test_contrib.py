import importlib
import sys

import pytest
from demo.models import Author, Book
from django.contrib import admin
from django.test import RequestFactory


@pytest.mark.parametrize(
    ("module", "dependency", "extra"),
    [
        ("django_admin_inline_controls.contrib.filters", "django_filters", "filters"),
        ("django_admin_inline_controls.contrib.nested", "nested_admin", "nested"),
        ("django_admin_inline_controls.contrib.unfold", "unfold", "unfold"),
    ],
)
def test_contrib_import_without_extra_raises_helpful_error(
    monkeypatch, module, dependency, extra
):
    monkeypatch.setitem(sys.modules, dependency, None)
    monkeypatch.delitem(sys.modules, module, raising=False)

    with pytest.raises(ImportError, match=rf"django-admin-inline-controls\[{extra}\]"):
        importlib.import_module(module)


@pytest.fixture
def get_request(admin_user):
    def make(data=None):
        request = RequestFactory().get("/", data or {})
        request.user = admin_user
        return request

    return make


@pytest.fixture
def filterset_inline():
    django_filters = pytest.importorskip("django_filters")
    from django_admin_inline_controls.contrib.filters import (
        FilterSetInlineControlsMixin,
    )

    class BookFilterSet(django_filters.FilterSet):
        min_pages = django_filters.NumberFilter(field_name="pages", lookup_expr="gte")

        class Meta:
            model = Book
            fields = ["status"]

        def __init__(self, *args, parent=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.parent = parent

    class BookInline(FilterSetInlineControlsMixin, admin.TabularInline):
        model = Book
        inline_per_page = 5
        inline_filterset_class = BookFilterSet

        def get_inline_filterset_kwargs(self, request, obj):
            return {"parent": obj}

    return BookInline(Author, admin.site)


def test_filterset_filters_the_inline(filterset_inline, author, get_request):
    request = get_request({"books-f-status": "published", "books-f-min_pages": "200"})
    formset_class = filterset_inline.get_formset(request, author)
    formset = formset_class(instance=author, prefix="books")

    assert [b.pages for b in formset.get_queryset()] == [210, 230, 250]
    controls = formset.inline_controls
    assert controls.total_count == 3
    assert controls.filter_param_names == ["books-f-status", "books-f-min_pages"]
    assert controls.filter_form.fields["status"].widget.attrs["form"] == (
        "books-inline-controls-filters"
    )


def test_filterset_receives_parent_and_request(filterset_inline, author, get_request):
    request = get_request()
    captured = {}
    filterset_class = filterset_inline.inline_filterset_class
    original_init = filterset_class.__init__

    def spy(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        captured.update(parent=self.parent, request=self.request)

    filterset_class.__init__ = spy
    try:
        filterset_inline.get_formset(request, author)(
            instance=author, prefix="books"
        ).get_queryset()
    finally:
        filterset_class.__init__ = original_init

    assert captured == {"parent": author, "request": request}


def test_filterset_mixin_without_filterset_falls_back_to_fields(author, get_request):
    pytest.importorskip("django_filters")
    from django_admin_inline_controls.contrib.filters import (
        FilterSetInlineControlsMixin,
    )

    class BookInline(FilterSetInlineControlsMixin, admin.TabularInline):
        model = Book
        inline_filter_fields = ["status"]

    request = get_request({"books-f-status": "draft"})
    formset = BookInline(Author, admin.site).get_formset(request, author)(
        instance=author, prefix="books"
    )

    assert formset.get_queryset().count() == 12


def test_nested_mixin_disables_ajax_and_infinite():
    pytest.importorskip("nested_admin")
    import nested_admin

    from django_admin_inline_controls.contrib.nested import NestedInlineControlsMixin

    class BookInline(NestedInlineControlsMixin, nested_admin.NestedTabularInline):
        model = Book
        inline_per_page = 5
        inline_pagination = "infinite"

    inline = BookInline(Author, admin.site)

    assert inline.inline_controls_ajax is False
    assert "admin_inline_controls.E101" in [e.id for e in inline.check()]


def test_nested_mixin_renders_in_nested_admin(admin_client, author):
    pytest.importorskip("nested_admin")
    response = admin_client.get(f"/test-admin/nested/demo/author/{author.pk}/change/")

    assert response.status_code == 200
    assert b'id="books-inline-controls"' in response.content
    assert b"&quot;ajax&quot;: false" in response.content


# django-unfold ---------------------------------------------------------------


@pytest.fixture
def unfold_mixin():
    pytest.importorskip("unfold")
    from django_admin_inline_controls.contrib.unfold import UnfoldInlineControlsMixin

    return UnfoldInlineControlsMixin


def unfold_inline(mixin, **attrs):
    inline_class = type(
        "BookInline", (mixin, admin.TabularInline), {"model": Book, **attrs}
    )
    return inline_class(Author, admin.AdminSite(name="unfold_site"))


def test_unfold_selectors_under_the_inline_own(unfold_mixin, get_request):
    from django_admin_inline_controls.contrib.unfold import UNFOLD_SELECTORS
    from django_admin_inline_controls.controls import DEFAULT_SELECTORS

    inline = unfold_inline(
        unfold_mixin, inline_controls_selectors={"row_label": ".mine"}
    )
    selectors = inline.get_inline_controls_selectors(get_request(), None)

    assert selectors["form_rows"] == UNFOLD_SELECTORS["form_rows"]
    assert selectors["saved_row"] == [".original"]
    assert selectors["row_label"] == [".mine"]
    assert selectors["heading"] == DEFAULT_SELECTORS["heading"]


def test_unfold_media(unfold_mixin):
    media = str(unfold_inline(unfold_mixin, inline_actions=["delete_selected"]).media)

    for path in ["js/core.js", "js/actions.js", "js/contrib/unfold.js"]:
        assert f"django_admin_inline_controls/{path}" in media
    assert "css/core.css" in media
    assert "css/contrib/unfold.css" in media


def test_unfold_per_page_is_an_error(unfold_mixin):
    ids = lambda inline: [error.id for error in inline.check()]  # noqa: E731

    assert "admin_inline_controls.E104" in ids(unfold_inline(unfold_mixin, per_page=10))
    assert "admin_inline_controls.E104" not in ids(unfold_inline(unfold_mixin))
