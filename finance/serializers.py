# finance/serializers.py
from rest_framework import serializers
from .models import Category, POCKET_TYPES, MoneyTx


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id",
            "pocket_type",
            "name",
            "icon_name",
            "color_hex",
            "order",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_default", "created_at", "updated_at"]

    def validate_pocket_type(self, v: str) -> str:
        if v not in dict(POCKET_TYPES):
            raise serializers.ValidationError("pocket_type inválido.")
        return v

    def validate_color_hex(self, v: str) -> str:
        v = v.strip()
        if not v.startswith("#") or len(v) not in (7, 9):
            raise serializers.ValidationError(
                "color_hex debe ser #RRGGBB o #AARRGGBB."
            )
        return v

    def create(self, validated_data):
        # El usuario siempre es el autenticado
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class MoneyTxSerializer(serializers.ModelSerializer):
    """
    El front usa "category" como string -> mapeado a category_name.
    pocket_type es el bolsillo real ('ingreso', 'gasto', 'ahorro', 'inversion').
    """

    category = serializers.CharField(source="category_name")
    pocket_type = serializers.ChoiceField(
        choices=[k for (k, _) in POCKET_TYPES]
    )
    category_id = serializers.IntegerField(
        source="category.id",
        read_only=True,
    )

    class Meta:
        model = MoneyTx
        fields = [
            "id",
            "pocket_type",  # bolsillo real
            "type",         # solo visual (ingreso|gasto)
            "category",
            "category_id",
            "amount",
            "currency",
            "date",
            "payment",
            "is_fixed",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "category_id", "created_at", "updated_at"]

    def validate_type(self, v: str) -> str:
        if v not in ("ingreso", "gasto"):
            raise serializers.ValidationError("type inválido (ingreso|gasto).")
        return v

    def validate_currency(self, v: str) -> str:
        v = (v or "").upper().strip()
        if len(v) != 3:
            raise serializers.ValidationError(
                "currency debe ser código ISO-4217 de 3 letras."
            )
        return v

    def _resolve_category(self, user, pocket_type: str, name: str):
        try:
            return Category.objects.get(
                user=user,
                pocket_type=pocket_type,
                name=name,
            )
        except Category.DoesNotExist:
            return None

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["user"] = user

        name = validated_data.get("category_name")
        pocket = validated_data.get("pocket_type")

        if name and pocket:
            validated_data["category"] = self._resolve_category(
                user, pocket, name
            )
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # user nunca cambia
        validated_data.pop("user", None)
        user = self.context["request"].user

        pocket = validated_data.get("pocket_type", instance.pocket_type)
        name = validated_data.get("category_name", instance.category_name)

        if pocket and name:
            validated_data["category"] = self._resolve_category(
                user, pocket, name
            )

        return super().update(instance, validated_data)
