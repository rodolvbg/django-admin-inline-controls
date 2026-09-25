import pytest
from demo.models import Author, Book
from django.contrib import admin

from django_admin_inline_controls.mixins import InlineControlsMixin


def check_ids(**attrs):
    inline_class = type(
        "BookInline",
        (InlineControlsMixin, admin.TabularInline),
        {"model": Book, "__module__": __name__, **attrs},
    )
    return [error.id for error in inline_class(Author, admin.site).check()]


def test_valid_configuration_has_no_errors():
    assert (
        check_ids(
            inline_per_page=10,
            inline_pagination="infinite",
            inline_ordering_fields={"title": "title"},
            inline_filter_fields=["status", "author__name__icontains"],
        )
        == []
    )


@pytest.mark.parametrize(
    ("attrs", "error_id"),
    [
        ({"inline_pagination": "nope"}, "admin_inline_controls.E001"),
        ({"inline_per_page": 0}, "admin_inline_controls.E002"),
        ({"inline_per_page": "10"}, "admin_inline_controls.E002"),
        ({"inline_per_page": True}, "admin_inline_controls.E002"),
        ({"inline_pagination": "infinite"}, "admin_inline_controls.E003"),
        ({"inline_filter_fields": "status"}, "admin_inline_controls.E004"),
        ({"inline_filter_fields": ["nope"]}, "admin_inline_controls.E005"),
        ({"inline_ordering_fields": "title"}, "admin_inline_controls.E006"),
        ({"inline_ordering_fields": ["-title"]}, "admin_inline_controls.E007"),
        ({"inline_ordering_fields": ["a,b"]}, "admin_inline_controls.E007"),
    ],
)
def test_invalid_configuration(attrs, error_id):
    assert error_id in check_ids(**attrs)
