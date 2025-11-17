# auth_otp/admin.py
from django.contrib import admin
from .models import OtpCode


@admin.register(OtpCode)
class OtpCodeAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "code", "used", "created_at", "expires_at", "attempts")
    search_fields = ("email", "code")
    list_filter = ("used",)
    ordering = ("-created_at",)
