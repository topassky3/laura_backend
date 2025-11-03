# auth_otp/views.py
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.parsers import JSONParser, FormParser
from rest_framework.throttling import ScopedRateThrottle

from .serializers import RequestOtpSerializer, VerifyOtpSerializer
from . import otp_service

User = get_user_model()


def _issue_tokens_for(user):
    """
    Genera par de tokens (access/refresh) para el usuario dado.
    """
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class RequestOtpView(APIView):
    """
    POST /api/auth/request-otp/
    body: { "email": "<correo>" }

    Crea un OTP aleatorio con TTL y lo envía por email (vía otp_service).
    En DEV (si SHOW_DEV_HINTS=1 y DEBUG=1) puede incluir pistas.
    """
    permission_classes = [permissions.AllowAny]
    parser_classes = [JSONParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp_send"

    def post(self, request):
        serializer = RequestOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower().strip()

        # Crea y envía OTP (Redis + TTL o fallback DB, según tu otp_service)
        otp_service.create_and_send(email)

        payload = {"detail": "Código enviado"}
        # Solo muestras pistas si SHOW_DEV_HINTS=True y DEBUG=True (definido en settings)
        if getattr(settings, "SHOW_DEV_HINTS", False):
            payload.update({
                "dev_hint_valid": getattr(settings, "OTP_DEV_FIXED", None),
                "dev_hint_bypass": getattr(settings, "OTP_BYPASS", None),
            })

        return Response(payload, status=status.HTTP_200_OK)


class VerifyOtpView(APIView):
    """
    POST /api/auth/verify-otp/
    body: { "email": "<correo>", "code": "<código>" }

    Verifica el OTP. Si es válido, emite JWTs.
    El BYPASS solo funciona si OTP_BYPASS_ENABLED=1 (en settings/env).
    """
    permission_classes = [permissions.AllowAny]
    parser_classes = [JSONParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp_verify"

    def post(self, request):
        serializer = VerifyOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].lower().strip()
        code = serializer.validated_data["code"].strip()

        # BYPASS: desactivado por defecto en Opción A (solo si OTP_BYPASS_ENABLED=1)
        if getattr(settings, "OTP_BYPASS_ENABLED", False) and code == getattr(settings, "OTP_BYPASS", ""):
            user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
            return Response(
                {
                    "detail": "Login por BYPASS",
                    "tokens": _issue_tokens_for(user),
                    "profile": {"email": email},
                },
                status=status.HTTP_200_OK,
            )

        # Verificación real (Redis/DB) vía otp_service
        if not otp_service.verify(email, code):
            return Response({"detail": "Código inválido o expirado."}, status=status.HTTP_400_BAD_REQUEST)

        user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
        return Response(
            {
                "detail": "Verificado",
                "tokens": _issue_tokens_for(user),
                "profile": {"email": email},
            },
            status=status.HTTP_200_OK,
        )

class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response({
            "email": u.email or u.username,
            "username": u.username,
            # aquí puedes sumar campos de perfil cuando los tengas
        }, status=status.HTTP_200_OK)