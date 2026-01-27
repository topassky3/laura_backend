from __future__ import annotations

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from banking.models import BankAlert, PlaidItem


class Command(BaseCommand):
    help = "Crea una BankAlert de prueba (sin depender de Plaid) para testear banner/notificaciones."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, default=0, help="ID del usuario")
        parser.add_argument("--email", type=str, default="", help="Email del usuario")

        parser.add_argument(
            "--kind",
            type=str,
            default="income",
            help="Tipo de alerta: income | expense",
        )

        parser.add_argument("--amount", type=str, default="1200.00", help="Monto (ej 1200.00)")
        parser.add_argument("--currency", type=str, default="USD", help="Moneda (ej USD)")

        # ✅ Ahora default dinámico según kind:
        parser.add_argument("--title", type=str, default="", help="Título (opcional)")
        parser.add_argument("--message", type=str, default="", help="Mensaje (opcional)")

    def handle(self, *args, **opts):
        user_id = int(opts["user_id"] or 0)
        email = (opts["email"] or "").strip()

        User = get_user_model()

        if email:
            u = User.objects.filter(email__iexact=email).first()
            if not u:
                self.stdout.write(self.style.ERROR(f"No existe usuario con email={email}"))
                return
        else:
            if not user_id:
                self.stdout.write(self.style.ERROR("Pasa --user-id o --email"))
                return
            u = User.objects.filter(id=user_id).first()
            if not u:
                self.stdout.write(self.style.ERROR(f"No existe usuario con id={user_id}"))
                return

        item = PlaidItem.objects.filter(user=u).order_by("-updated_at").first()
        if not item:
            self.stdout.write(self.style.ERROR("Ese usuario no tiene PlaidItem. Conecta un banco primero."))
            return

        kind = (opts["kind"] or "income").strip().lower()
        if kind not in {BankAlert.KIND_INCOME, BankAlert.KIND_EXPENSE}:
            self.stdout.write(self.style.ERROR("kind inválido. Usa: income | expense"))
            return

        amount = Decimal(str(opts["amount"] or "0")).copy_abs()
        currency = (opts["currency"] or "USD").strip().upper()

        title = (opts["title"] or "").strip()
        message = (opts["message"] or "").strip()

        if not title:
            title = "Ingreso detectado 💰 (TEST)" if kind == BankAlert.KIND_INCOME else "Gasto detectado 💸 (TEST)"
        if not message:
            message = "Nómina (manual test)" if kind == BankAlert.KIND_INCOME else "Compra (manual test)"

        a = BankAlert.objects.create(
            user=u,
            item=item,
            kind=kind,
            title=title,
            message=message,
            amount=amount,
            currency=currency,
        )

        self.stdout.write(self.style.SUCCESS(
            f"✅ BankAlert creada: id={a.id} kind={a.kind} user_id={u.id} item_id={item.item_id}"
        ))
