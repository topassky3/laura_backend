from rest_framework import serializers


class CreateLinkTokenSerializer(serializers.Serializer):
    # ✅ Flutter enviará el package real del APK
    android_package_name = serializers.CharField(required=False, allow_blank=True, max_length=255)


class ExchangePublicTokenSerializer(serializers.Serializer):
    public_token = serializers.CharField(min_length=5, max_length=2048)
    metadata = serializers.DictField(required=False)
