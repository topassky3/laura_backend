from rest_framework import serializers

from .models import BankAlert


class CreateLinkTokenSerializer(serializers.Serializer):
    android_package_name = serializers.CharField(required=False, allow_blank=True, max_length=255)


class ExchangePublicTokenSerializer(serializers.Serializer):
    public_token = serializers.CharField(min_length=5, max_length=2048)
    metadata = serializers.DictField(required=False)


# ✅ NUEVO: alerts
class BankAlertSerializer(serializers.ModelSerializer):
    institution_name = serializers.SerializerMethodField()

    class Meta:
        model = BankAlert
        fields = (
            "id",
            "kind",
            "title",
            "message",
            "amount",
            "currency",
            "institution_name",
            "created_at",
        )

    def get_institution_name(self, obj: BankAlert) -> str:
        try:
            return (obj.item.institution_name or "").strip()
        except Exception:
            return ""


class AckAlertsSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )
