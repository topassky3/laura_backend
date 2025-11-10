from django.contrib import admin
from .models import Category, MoneyTx

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("user", "pocket_type", "name", "order", "is_default")
    list_filter = ("pocket_type", "is_default")
    search_fields = ("name", "user__username", "user__email")


@admin.register(MoneyTx)
class MoneyTxAdmin(admin.ModelAdmin):
    list_display = ("user", "pocket_type", "type", "category_label", "amount",
                    "currency", "payment", "date", "is_fixed")
    list_filter = ("pocket_type", "type", "payment", "currency", "is_fixed")
    search_fields = ("category_name", "note", "user__username", "user__email")
    ordering = ("-date", "-id")

    def category_label(self, obj):
        return obj.category.name if obj.category_id else obj.category_name
    category_label.short_description = "Categoría"
