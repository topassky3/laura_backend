from django.contrib import admin
from .models import Category

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("user", "pocket_type", "name", "order", "is_default")
    list_filter = ("pocket_type", "is_default")
    search_fields = ("name", "user__username", "user__email")
