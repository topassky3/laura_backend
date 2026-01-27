from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from banking.models import BankAlert, PlaidItem
from banking.services.plaid_http_client import PlaidApiError, PlaidHttpClient, load_plaid_config
from banking.services.plaid_sync import sync_transactions_for_item


class Command(BaseCommand):
    help = "Crea un 'gasto' de prueba en Plaid Sandbox y fuerza sync para generar BankAlert(kind=expense)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--amount",
            type=float,
            default=35.0,
            help="Monto absoluto. Para gasto se enviará positivo (default: 35.0).",
        )
        parser.add_argument(
            "--description",
            type=str,
            default="Compra (Sandbox)",
            help="Descripción de la transacción (default: 'Compra (Sandbox)')",
        )
        parser.add_argument(
            "--currency",
            type=str,
            default="USD",
            help="ISO currency code (default: USD)",
        )
        parser.add_argument(
            "--item-id",
            type=str,
            default="",
            help="Item ID exacto (opcional). Si no, usa el PlaidItem más reciente.",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            default=0,
            help="Filtra por user_id (opcional).",
        )

    def handle(self, *args, **opts):
        amount_abs = float(opts["amount"])
        description = (opts["description"] or "").strip() or "Compra (Sandbox)"
        currency = (opts["currency"] or "USD").strip().upper() or "USD"
        item_id = (opts["item_id"] or "").strip()
        user_id = int(opts["user_id"] or 0)

        qs = PlaidItem.objects.all().order_by("-updated_at")
        if user_id:
            qs = qs.filter(user_id=user_id)
        if item_id:
            qs = qs.filter(item_id=item_id)

        item = qs.first()
        if not item:
            self.stdout.write(self.style.ERROR("No encontré PlaidItem. Conecta un banco primero."))
            return

        today = timezone.localdate().isoformat()

        # Gasto = positivo
        payload = {
            "amount": abs(amount_abs),
            "date_posted": today,
            "date_transacted": today,
            "description": description,
            "iso_currency_code": currency,
        }

        cfg = load_plaid_config()
        client = PlaidHttpClient(cfg)

        self.stdout.write(f"Usando PlaidItem: item_id={item.item_id} user_id={item.user_id}")
        self.stdout.write(f"Creando transacción sandbox: {payload}")

        try:
            r = client.sandbox_transactions_create(access_token=item.access_token, transactions=[payload])
            self.stdout.write(self.style.SUCCESS(f"Plaid OK: request_id={r.get('request_id')}"))
        except PlaidApiError as e:
            self.stdout.write(self.style.ERROR(f"PlaidApiError ({e.status_code}): {e}"))
            if getattr(e, "details", None):
                self.stdout.write(str(e.details))
            return

        sync_res = sync_transactions_for_item(item)

        unseen = BankAlert.objects.filter(user=item.user, seen_at__isnull=True).order_by("-created_at")[:10]
        self.stdout.write(
            self.style.WARNING(
                f"SYNC: added={sync_res.added} modified={sync_res.modified} removed={sync_res.removed} "
                f"new_income_alerts={sync_res.new_income_alerts} new_expense_alerts={sync_res.new_expense_alerts}"
            )
        )

        if sync_res.new_expense_alerts == 0:
            self.stdout.write(
                self.style.ERROR(
                    "No se generaron alertas de gasto. OJO: /sandbox/transactions/create SOLO funciona si "
                    "el Item fue creado con el usuario sandbox 'user_transactions_dynamic'."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("✅ Alertas creadas. Últimas no-vistas:"))
            for a in unseen:
                self.stdout.write(f"- id={a.id} kind={a.kind} amount={a.amount} {a.currency} title={a.title} msg={a.message}")
