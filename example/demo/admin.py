from django.contrib import admin

from django_admin_inline_controls.mixins import ExampleMixin

from .models import Item


@admin.register(Item)
class ItemAdmin(ExampleMixin):
    list_display = ["name"]
