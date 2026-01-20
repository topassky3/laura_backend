from django.contrib import admin

from .models import BankAlert, PlaidAccount, PlaidItem, PlaidTransaction


@admin.register(PlaidItem)
class PlaidItemAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "item_id", "institution_name", "last_synced_at", "created_at")
    search_fields = ("item_id", "institution_name", "user__email", "user__username")
    list_filter = ("created_at", "last_synced_at")


@admin.register(PlaidAccount)
class PlaidAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "item", "account_id", "name", "mask", "type", "subtype")
    search_fields = ("account_id", "name", "mask")


@admin.register(PlaidTransaction)
class PlaidTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "item", "transaction_id", "date", "name", "amount", "pending")
    search_fields = ("transaction_id", "name", "merchant_name")
    list_filter = ("pending", "date", "created_at")


@admin.register(BankAlert)
class BankAlertAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "title", "amount", "currency", "seen_at", "created_at")
    list_filter = ("kind", "seen_at", "created_at")
    search_fields = ("title", "message", "user__email")
