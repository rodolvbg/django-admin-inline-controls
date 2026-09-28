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

# A file, not ":memory:": an in-memory test database is one connection shared
# by every live_server thread, so two concurrent browser requests in the e2e
# tests (e.g. an infinite-scroll fetch racing a form submit) corrupt each
# other's transactions. With a file each thread gets its own connection.
# One file per process, so parallel runs (tox run-parallel) don't collide.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {
            "NAME": str(
                Path(tempfile.gettempdir())
                / f"django-admin-inline-controls-{os.getpid()}.sqlite3"
            )
        },
    }
}

STATIC_URL = "static/"

USE_TZ = True
