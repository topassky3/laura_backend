from rest_framework import serializers

class RequestOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()

class VerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(min_length=1, max_length=6)
