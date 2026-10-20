import ast
import datetime
import gettext
import json
import re
from pathlib import Path
from typing import Any

import pytest
from demo.models import Article, Author, Book
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

LOCALE_DIR = Path(__file__).parent.parent / "src/django_admin_inline_controls/locale"
CATALOGS = sorted(LOCALE_DIR.glob("*/LC_MESSAGES/django.po"))
CATALOG_IDS = [c.parent.parent.name for c in CATALOGS]


def po_entries(path):
    """``(msgid, [msgstr...], fuzzy)`` for every message of a .po file."""
    for block in path.read_text(encoding="utf-8").split("\n\n"):
        msgid = re.search(r'^msgid "(.*)"', block, re.M)
        if not msgid or 'msgid ""\nmsgstr ""\n"' in block:
            continue
        yield (
            msgid.group(1),
            re.findall(r'^msgstr(?:\[\d+\])? "(.*)"$', block, re.M),
            "#, fuzzy" in block,
        )


PO_LINE = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?) (".*")$')


def po_messages(path):
    """``{msgid: msgstr}`` (``{(msgid, n): msgstr}`` for plurals) of a .po file."""
    messages: dict[Any, str] = {}
    for block in path.read_text(encoding="utf-8").split("\n\n"):
        fields: dict[str, str] = {}
        key = None
        for line in block.splitlines():
            match = PO_LINE.match(line)
            if match:
                key = match.group(1)
                fields[key] = ast.literal_eval(match.group(2))
            elif line.startswith('"') and key:
                fields[key] += ast.literal_eval(line)
        msgid = fields.get("msgid")
        if not msgid or "#, fuzzy" in block:
            continue
        if "msgctxt" in fields:
            msgid = f"{fields['msgctxt']}\x04{msgid}"
        if "msgid_plural" in fields:
            for name, value in fields.items():
                if name.startswith("msgstr["):
                    messages[(msgid, int(name[7:-1]))] = value
        else:
            messages[msgid] = fields["msgstr"]
    return messages


def mo_messages(path):
    """The same, from the compiled .mo (as Django will load it)."""
    with path.open("rb") as file:
        catalog = getattr(gettext.GNUTranslations(file), "_catalog")  # noqa: B009
    return {key: value for key, value in catalog.items() if key != ""}


@pytest.mark.parametrize("catalog", CATALOGS, ids=CATALOG_IDS)
class TestCatalogs:
    """The shipped message catalogs."""

    def test_every_message_is_translated(self, catalog):
        problems = [
            msgid
            for msgid, msgstrs, fuzzy in po_entries(catalog)
            if fuzzy or not all(s.strip() for s in msgstrs)
        ]
        assert problems == []

    def test_compiled_catalog_is_up_to_date(self, catalog):
        """The shipped .mo has exactly the .po's translations (not compared by
        date: a git checkout gives both files arbitrary modification times)."""
        compiled = catalog.with_suffix(".mo")

        assert compiled.exists()
        assert mo_messages(compiled) == po_messages(catalog)


class TestSpanishRendering(TestCase):
    """Rendering in Spanish."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        cls.author = Author.objects.create(name="Author")
        statuses = [Book.Status.DRAFT, Book.Status.PUBLISHED]
        Book.objects.bulk_create(
            Book(
                author=cls.author,
                title=f"Book {n:02d}",
                status=statuses[n % 2],
                published=datetime.date(2020, 1, 1) + datetime.timedelta(days=n),
                pages=10 * n,
                featured=n % 5 == 0,
            )
            for n in range(1, 26)
        )
        Article.objects.bulk_create(
            Article(author=cls.author, title=f"Article {n:02d}", words=n)
            for n in range(1, 21)
        )

    def setUp(self):
        self.client.force_login(self.user)
        url = reverse("admin:demo_author_change", args=[self.author.pk])
        with translation.override("es"):
            self.spanish_page = self.client.get(url)

    def test_toolbar_and_footer_in_spanish(self):
        html = self.spanish_page.content.decode()

        # Identical to Django admin messages: the admin's translation wins (it is
        # listed first in INSTALLED_APPS), consistent with the changelist.
        assert ">Filtro</button>" in html
        assert "Ordenar por:" in html
        assert "Acción:" in html
        assert "25 resultados" in html
        assert "Guardar books" in html  # the model's own verbose name is untouched
        assert "Mostrando 15 de 20" in html

    def test_generated_filter_labels_and_choices_in_spanish(self):
        html = self.spanish_page.content.decode()

        assert "Title (contiene)" in html
        assert "Published (desde)" in html
        assert '<option value="true">Sí</option>' in html

    def test_actions_and_js_messages_in_spanish(self):
        html = self.spanish_page.content.decode()
        controls = self.spanish_page.context["inline_admin_formsets"][
            0
        ].formset.inline_controls
        with translation.override("es"):  # config_json is computed lazily
            config = json.loads(controls.config_json)

        assert "Eliminar books seleccionado/s" in html  # the admin's own wording
        assert config["messages"]["selected"] == "%(sel)s de %(cnt)s seleccionados"
        assert config["bulkActions"][2]["confirmation"] == (
            "¿Eliminar %(count)s books seleccionados? No se puede deshacer."
        )

    def test_delete_selected_message_is_pluralized(self):
        url = reverse(
            "admin:demo_author_inline_controls_action", args=[self.author.pk, "books"]
        )
        pks = list(self.author.books.order_by("pk").values_list("pk", flat=True)[:2])
        with translation.override("es"):
            one = self.client.post(
                url, {"action": "delete_selected", "_selected_action": pks[:1]}
            )
            two = self.client.post(
                url, {"action": "delete_selected", "_selected_action": pks[1:]}
            )

        assert "Se eliminó 1 book." in one.content.decode()
        assert "Se eliminó 1 book." in two.content.decode()
