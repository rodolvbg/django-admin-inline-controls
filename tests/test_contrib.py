import importlib
import sys

import pytest


@pytest.mark.parametrize(
    ("module", "dependency", "extra"),
    [
        ("django_admin_inline_controls.contrib.filters", "django_filters", "filters"),
        ("django_admin_inline_controls.contrib.nested", "nested_admin", "nested"),
    ],
)
def test_contrib_import_without_extra_raises_helpful_error(
    monkeypatch, module, dependency, extra
):
    monkeypatch.setitem(sys.modules, dependency, None)
    monkeypatch.delitem(sys.modules, module, raising=False)

    with pytest.raises(ImportError, match=rf"django-admin-inline-controls\[{extra}\]"):
        importlib.import_module(module)


@pytest.mark.parametrize(
    ("module", "dependency"),
    [
        ("django_admin_inline_controls.contrib.filters", "django_filters"),
        ("django_admin_inline_controls.contrib.nested", "nested_admin"),
    ],
)
def test_contrib_import_with_extra_installed(monkeypatch, module, dependency):
    pytest.importorskip(dependency)
    monkeypatch.delitem(sys.modules, module, raising=False)

    importlib.import_module(module)
