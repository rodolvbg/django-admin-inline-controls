"""InlineOrderingMixin: the ordering of each column."""

from django.db.models import F
from django.db.models.functions import Lower
from django.test import SimpleTestCase
from unittest_parametrize import ParametrizedTestCase, parametrize

from django_admin_inline_controls.controls import (
    normalize_ordering_fields,
    ordering_expression,
)


class TestOrderingExpression(ParametrizedTestCase, SimpleTestCase):
    """Turning ordering values into query expressions."""

    @parametrize(
        ("value", "descending", "expected"),
        [
            ("title", False, "title"),
            ("title", True, "-title"),
            ("-title", False, "-title"),
            ("-title", True, "title"),
            (("a", "-b"), True, "-b"),
            (("a", "-b"), False, "a"),
        ],
    )
    def test_ordering_expression_strings(self, value, descending, expected):
        assert ordering_expression(value, descending) == expected

    def test_ordering_expression_expressions(self):
        assert ordering_expression(Lower("title"), True) == Lower("title").desc()
        assert ordering_expression(Lower("title"), False) == Lower("title").asc()

        asc = F("published").asc(nulls_last=True)
        assert ordering_expression(asc, False) is asc
        reversed_ = ordering_expression(asc, True)
        assert reversed_.descending
        assert not asc.descending  # the declared expression is not mutated


class TestNormalizeOrderingFields(ParametrizedTestCase, SimpleTestCase):
    """Normalizing the ordering fields option."""

    @parametrize(
        ("value", "expected"),
        [
            (["a", "b"], {"a": "a", "b": "b"}),
            ({"a": "x"}, {"a": "x"}),
        ],
        ids=["list", "dict"],
    )
    def test_normalize_ordering_fields(self, value, expected):
        assert normalize_ordering_fields(value) == expected
