# banking/views.py
from typing import Any, Dict

from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PlaidAccount, PlaidItem
from .serializers import ExchangePublicTokenSerializer, CreateLinkTokenSerializer
from .services.plaid_http_client import PlaidApiError, PlaidHttpClient, load_plaid_config


def _ok(data: Dict[str, Any], status_code: int = 200) -> Response:
    return Response(data, status=status_code)


def _err(message: str, *, status_code: int = 400, details: dict | None = None) -> Response:
    payload: Dict[str, Any] = {"detail": message}
    if details:
        payload["extra"] = details
    return Response(payload, status=status_code)


class PlaidLinkTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            cfg = load_plaid_config()
            client = PlaidHttpClient(cfg)

            ser = CreateLinkTokenSerializer(data=request.data or {})
            ser.is_valid(raise_exception=True)

            android_pkg = (ser.validated_data.get("android_package_name") or "").strip()

            data = client.create_link_token(
                client_user_id=str(request.user.pk),
                android_package_name=android_pkg,
            )

            return _ok({"link_token": data.get("link_token"), "expiration": data.get("expiration")})

        except PlaidApiError as e:
            return _err(str(e), status_code=e.status_code, details=getattr(e, "details", None))
        except Exception as e:
            return _err(f"Error interno creando link_token: {e}", status_code=500)


class PlaidExchangePublicTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = ExchangePublicTokenSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        public_token = ser.validated_data["public_token"]
        metadata = ser.validated_data.get("metadata") or {}

        institution = metadata.get("institution") or {}
        inst_id = institution.get("id") or ""
        inst_name = institution.get("name") or ""
        accounts = metadata.get("accounts") or []

        try:
            cfg = load_plaid_config()
            client = PlaidHttpClient(cfg)

            ex = client.exchange_public_token(public_token=public_token)
            access_token = ex.get("access_token")
            item_id = ex.get("item_id")

            if not access_token or not item_id:
                return _err("Respuesta inválida de Plaid: falta access_token/item_id", status_code=502)

            with transaction.atomic():
                existing = (
                    PlaidItem.objects.select_for_update()
                    .filter(item_id=item_id)
                    .first()
                )
                if existing and existing.user_id != request.user.id:
                    return _err(
                        "Este banco ya está vinculado a otra cuenta. "
                        "Si crees que es un error, contacta soporte.",
                        status_code=409,
                        details={"item_id": item_id},
                    )

                if existing:
                    existing.access_token = access_token
                    existing.institution_id = inst_id
                    existing.institution_name = inst_name
                    existing.user = request.user
                    existing.save(update_fields=["access_token", "institution_id", "institution_name", "user", "updated_at"])
                    item = existing
                else:
                    item = PlaidItem.objects.create(
                        user=request.user,
                        item_id=item_id,
                        access_token=access_token,
                        institution_id=inst_id,
                        institution_name=inst_name,
                    )

                for a in accounts:
                    if not isinstance(a, dict):
                        continue
                    acc_id = a.get("id") or ""
                    if not acc_id:
                        continue

                    PlaidAccount.objects.update_or_create(
                        item=item,
                        account_id=acc_id,
                        defaults={
                            "mask": a.get("mask") or "",
                            "name": a.get("name") or "",
                            "type": a.get("type") or "",
                            "subtype": a.get("subtype") or "",
                            "verification_status": a.get("verification_status") or "",
                        },
                    )

            return _ok({"status": "ok"})

        except (ProgrammingError, OperationalError) as e:
            return _err(
                "Base de datos sin migraciones del app 'banking'. "
                "Crea/aplica migraciones y vuelve a intentar.",
                status_code=500,
                details={
                    "hint": "Ejecuta: python manage.py makemigrations banking && python manage.py migrate",
                    "db_error": str(e),
                },
            )

        except PlaidApiError as e:
            return _err(str(e), status_code=e.status_code, details=getattr(e, "details", None))
        except Exception as e:
            return _err(f"Error interno intercambiando public_token: {e}", status_code=500)


class PlaidStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            item = (
                PlaidItem.objects.filter(user=request.user)
                .order_by("-updated_at")
                .first()
            )

            if not item:
                return _ok({"connected": False})

            accounts_count = PlaidAccount.objects.filter(item=item).count()
            items_count = PlaidItem.objects.filter(user=request.user).count()

            return _ok(
                {
                    "connected": True,
                    "items_count": items_count,
                    "institution_id": item.institution_id,
                    "institution_name": item.institution_name,
                    "accounts_count": accounts_count,
                    "item_id": item.item_id,  # opcional debug
                }
            )
        except Exception as e:
            return _err(f"Error leyendo estado Plaid: {e}", status_code=500)


class PlaidDisconnectView(APIView):
    """
    Desconecta el banco del usuario:
    - Borra PlaidItem(s) del usuario (y por cascade borra PlaidAccount).
    - Resultado: /status/ vuelve a connected=false.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            with transaction.atomic():
                qs = PlaidItem.objects.filter(user=request.user)
                removed = qs.count()
                qs.delete()

            return _ok({"status": "ok", "removed_items": removed})

        except (ProgrammingError, OperationalError) as e:
            return _err(
                "Base de datos sin migraciones del app 'banking'. "
                "Crea/aplica migraciones y vuelve a intentar.",
                status_code=500,
                details={
                    "hint": "Ejecuta: python manage.py makemigrations banking && python manage.py migrate",
                    "db_error": str(e),
                },
            )
        except Exception as e:
            return _err(f"Error interno desconectando banco: {e}", status_code=500)
