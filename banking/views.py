from __future__ import annotations

from typing import Any, Dict

from django.db import transaction
from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BankAlert, PlaidAccount, PlaidItem
from .serializers import (
    AckAlertsSerializer,
    BankAlertSerializer,
    CreateLinkTokenSerializer,
    ExchangePublicTokenSerializer,
)
from .services.plaid_http_client import PlaidApiError, PlaidHttpClient, load_plaid_config
from .services.plaid_sync import sync_transactions_for_user


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
                        tx_cursor="",
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
    - Revoca access_token en Plaid (item/remove)
    - Borra PlaidItem(s) del usuario (y por cascade borra cuentas/transacciones/alertas).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            cfg = load_plaid_config()
            client = PlaidHttpClient(cfg)

            with transaction.atomic():
                items = list(PlaidItem.objects.filter(user=request.user))
                removed = len(items)

                # Revocar en Plaid (si falla, igual borramos local para que el usuario "se desconecte")
                for it in items:
                    try:
                        client.item_remove(access_token=it.access_token)
                    except Exception:
                        # Silencioso: no bloquea desconexión local
                        pass

                PlaidItem.objects.filter(user=request.user).delete()

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


# ✅ NUEVO: Forzar sync desde la app (para detectar ingresos "en vivo" mientras está abierta)
class PlaidSyncNowView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            summary = sync_transactions_for_user(request.user)
            return _ok({"status": "ok", **summary})
        except PlaidApiError as e:
            return _err(str(e), status_code=e.status_code, details=getattr(e, "details", None))
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
            return _err(f"Error interno sincronizando transacciones: {e}", status_code=500)


# ✅ NUEVO: listar alertas no vistas
class BankAlertsUnreadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            qs = (
                BankAlert.objects
                .select_related("item")
                .filter(user=request.user)
                .filter(seen_at__isnull=True)
                .order_by("-created_at")[:25]
            )
            return _ok({"alerts": BankAlertSerializer(qs, many=True).data})
        except Exception as e:
            return _err(f"Error leyendo alertas: {e}", status_code=500)


# ✅ NUEVO: ack (marcar como vistas)
class BankAlertsAckView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = AckAlertsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = ser.validated_data["ids"]

        try:
            now = timezone.now()
            updated = (
                BankAlert.objects
                .filter(user=request.user)
                .filter(id__in=ids)
                .filter(seen_at__isnull=True)
                .update(seen_at=now)
            )
            return _ok({"status": "ok", "acked": updated})
        except Exception as e:
            return _err(f"Error confirmando alertas: {e}", status_code=500)
