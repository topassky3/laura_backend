from rest_framework import serializers
from .models import Category, POCKET_TYPES

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "pocket_type", "name", "icon_name", "color_hex", "order", "is_default", "created_at", "updated_at"]
        read_only_fields = ["id", "is_default", "created_at", "updated_at"]

    def validate_pocket_type(self, v):
        if v not in dict(POCKET_TYPES):
            raise serializers.ValidationError("pocket_type inválido.")
        return v

    def validate_color_hex(self, v):
        v = v.strip()
        if not v.startswith("#") or len(v) not in (7, 9):
            raise serializers.ValidationError("color_hex debe ser #RRGGBB o #AARRGGBB.")
        return v

    def create(self, validated):
        # amarrar al usuario autenticado
        user = self.context["request"].user
        validated["user"] = user
        return super().create(validated)
