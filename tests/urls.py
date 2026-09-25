from django.contrib import admin
from django.urls import path

from tests.admin import nested_site
from tests.admin import site as test_admin_site

urlpatterns = [
    path("admin/", admin.site.urls),
    path("test-admin/", test_admin_site.urls),
]
if nested_site is not None:
    urlpatterns.insert(0, path("test-admin/nested/", nested_site.urls))
