from django.contrib import admin

from .models import PlaidAccount, PlaidItem


@admin.register(PlaidItem)
class PlaidItemAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "item_id", "institution_name", "created_at")
    search_fields = ("item_id", "institution_name", "user__email", "user__username")
    list_filter = ("created_at",)


@admin.register(PlaidAccount)
class PlaidAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "item", "account_id", "name", "mask", "type", "subtype")
    search_fields = ("account_id", "name", "mask")
