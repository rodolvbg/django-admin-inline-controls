import importlib.util
import os
import tempfile
from pathlib import Path

SECRET_KEY = "test-secret-key"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_admin_inline_controls",
    "demo",
]
if importlib.util.find_spec("nested_admin"):
    INSTALLED_APPS.append("nested_admin")

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "tests.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Files, not ":memory:". pytest-django's live_server shares one connection
# across all its threads when the database *looks* in-memory (it checks NAME
# before the test database exists), so two concurrent browser requests in
# the e2e tests (an infinite-scroll fetch racing a form submit) would use one
# SQLite connection at once: broken transactions or a segfault. With files,
# each thread gets its own connection. One pair per process, so parallel
# runs (tox run-parallel) don't collide.
_DB_BASE = Path(tempfile.gettempdir()) / f"django-admin-inline-controls-{os.getpid()}"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": f"{_DB_BASE}.sqlite3",
        "TEST": {"NAME": f"{_DB_BASE}-test.sqlite3"},
    }
}

STATIC_URL = "static/"

USE_TZ = True
