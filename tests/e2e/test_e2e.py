"""TEMPLATE — replace with a real end-to-end test, or delete tests/e2e/
entirely (and drop pytest-playwright/playwright from dependency-groups.dev)
if the library has no admin/browser surface worth covering this way.

Real end-to-end tests: drives an actual Chromium against a real Django
server (pytest-django's ``live_server`` fixture) — for exercising JS and
server-side behavior actually working together, not each mocked out for
the other. Slower than the rest of the suite; everything else belongs in
plain unit/integration tests instead.
"""

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import Page, expect


@pytest.mark.django_db(transaction=True)
def test_admin_login_loads(live_server, page: Page):
    User.objects.create_superuser("admin", "admin@example.com", "password")

    page.goto(f"{live_server.url}/admin/login/")
    page.fill("#id_username", "admin")
    page.fill("#id_password", "password")
    page.click("input[type=submit]")

    expect(page.locator("#site-name")).to_be_visible()
