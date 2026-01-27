from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable

from django.db import transaction as db_tx
from django.utils import timezone

from ..models import BankAlert, PlaidItem, PlaidTransaction
from .plaid_http_client import PlaidHttpClient, load_plaid_config


def _dec(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def _parse_date(s: Any) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s))
    except Exception:
        return None


def _tx_direction(raw_tx: Dict[str, Any]) -> str:
    return (raw_tx.get("transaction_type") or raw_tx.get("direction") or "").strip().upper()


def _is_income(raw_tx: Dict[str, Any]) -> bool:
    """
    Regla robusta:
    - Si viene transaction_type/direction = CREDIT => ingreso
    - Si no, amount < 0 => ingreso (en Plaid, CREDIT suele venir negativo)
    """
    ttype = _tx_direction(raw_tx)
    amt = _dec(raw_tx.get("amount", 0))
    if ttype == "CREDIT":
        return True
    if ttype == "DEBIT":
        return False
    return amt < 0


def _is_expense(raw_tx: Dict[str, Any]) -> bool:
    """
    Regla robusta:
    - Si viene transaction_type/direction = DEBIT => gasto
    - Si no, amount > 0 => gasto (en Plaid, DEBIT suele venir positivo)
    """
    ttype = _tx_direction(raw_tx)
    amt = _dec(raw_tx.get("amount", 0))
    if ttype == "DEBIT":
        return True
    if ttype == "CREDIT":
        return False
    return amt > 0


@dataclass
class SyncResult:
    added: int = 0
    modified: int = 0
    removed: int = 0
    new_income_alerts: int = 0
    new_expense_alerts: int = 0
    next_cursor: str = ""


def _tx_label(tx_obj: PlaidTransaction) -> str:
    return (tx_obj.merchant_name or tx_obj.name or "").strip() or "Movimiento"


def _tx_currency(tx_obj: PlaidTransaction) -> str:
    return (tx_obj.iso_currency_code or tx_obj.unofficial_currency_code or "").strip()


def _maybe_create_income_alert(*, item: PlaidItem, tx_obj: PlaidTransaction, raw_tx: Dict[str, Any]) -> bool:
    """
    Crea una alerta de ingreso si corresponde y si aún no existe.
    Retorna True si creó una alerta.
    """
    amount = _dec(raw_tx.get("amount", 0))
    pending = bool(raw_tx.get("pending", False))

    if pending:
        return False
    if amount == 0:
        return False
    if not _is_income(raw_tx):
        return False

    # Guardamos positivo para UI
    abs_amount = abs(amount)

    # Evitar duplicados: OneToOne con transaction
    if BankAlert.objects.filter(transaction=tx_obj).exists():
        return False

    BankAlert.objects.create(
        user=item.user,
        item=item,
        transaction=tx_obj,
        kind=BankAlert.KIND_INCOME,
        title="Ingreso detectado 💰",
        message=_tx_label(tx_obj),
        amount=abs_amount,
        currency=_tx_currency(tx_obj),
    )
    return True


def _maybe_create_expense_alert(*, item: PlaidItem, tx_obj: PlaidTransaction, raw_tx: Dict[str, Any]) -> bool:
    """
    Crea una alerta de gasto si corresponde y si aún no existe.
    Retorna True si creó una alerta.
    """
    amount = _dec(raw_tx.get("amount", 0))
    pending = bool(raw_tx.get("pending", False))

    if pending:
        return False
    if amount == 0:
        return False
    if not _is_expense(raw_tx):
        return False

    abs_amount = abs(amount)

    if BankAlert.objects.filter(transaction=tx_obj).exists():
        return False

    BankAlert.objects.create(
        user=item.user,
        item=item,
        transaction=tx_obj,
        kind=BankAlert.KIND_EXPENSE,
        title="Gasto detectado 💸",
        message=_tx_label(tx_obj),
        amount=abs_amount,
        currency=_tx_currency(tx_obj),
    )
    return True


def _upsert_transactions(
    *,
    item: PlaidItem,
    added: Iterable[Dict[str, Any]],
    modified: Iterable[Dict[str, Any]],
    removed: Iterable[Dict[str, Any]],
) -> SyncResult:
    res = SyncResult()

    def _maybe_alert(obj: PlaidTransaction, tx: Dict[str, Any]) -> None:
        # Solo una alerta por transacción (income XOR expense)
        if _maybe_create_income_alert(item=item, tx_obj=obj, raw_tx=tx):
            res.new_income_alerts += 1
            return
        if _maybe_create_expense_alert(item=item, tx_obj=obj, raw_tx=tx):
            res.new_expense_alerts += 1

    # ADDED
    for tx in added:
        txid = (tx.get("transaction_id") or "").strip()
        if not txid:
            continue

        amount = _dec(tx.get("amount", 0))
        pending = bool(tx.get("pending", False))

        obj, _created = PlaidTransaction.objects.update_or_create(
            transaction_id=txid,
            defaults={
                "item": item,
                "account_id": (tx.get("account_id") or "").strip(),
                "name": (tx.get("name") or "").strip(),
                "merchant_name": (tx.get("merchant_name") or "").strip(),
                "amount": amount,
                "iso_currency_code": (tx.get("iso_currency_code") or "").strip(),
                "unofficial_currency_code": (tx.get("unofficial_currency_code") or "").strip(),
                "date": _parse_date(tx.get("date")),
                "authorized_date": _parse_date(tx.get("authorized_date")),
                "pending": pending,
                "transaction_type": (tx.get("transaction_type") or tx.get("direction") or "").strip(),
                "raw": tx,
            },
        )

        res.added += 1
        _maybe_alert(obj, tx)

    # MODIFIED
    for tx in modified:
        txid = (tx.get("transaction_id") or "").strip()
        if not txid:
            continue

        amount = _dec(tx.get("amount", 0))
        pending = bool(tx.get("pending", False))

        obj, _created = PlaidTransaction.objects.update_or_create(
            transaction_id=txid,
            defaults={
                "item": item,
                "account_id": (tx.get("account_id") or "").strip(),
                "name": (tx.get("name") or "").strip(),
                "merchant_name": (tx.get("merchant_name") or "").strip(),
                "amount": amount,
                "iso_currency_code": (tx.get("iso_currency_code") or "").strip(),
                "unofficial_currency_code": (tx.get("unofficial_currency_code") or "").strip(),
                "date": _parse_date(tx.get("date")),
                "authorized_date": _parse_date(tx.get("authorized_date")),
                "pending": pending,
                "transaction_type": (tx.get("transaction_type") or tx.get("direction") or "").strip(),
                "raw": tx,
                "updated_at": timezone.now(),
            },
        )

        res.modified += 1

        # ✅ CLAVE: si antes estaba pending y ahora ya no, aquí se crea la alerta.
        _maybe_alert(obj, tx)

    # REMOVED
    for tx in removed:
        txid = (tx.get("transaction_id") or "").strip()
        if not txid:
            continue
        deleted, _ = PlaidTransaction.objects.filter(transaction_id=txid).delete()
        if deleted:
            res.removed += 1

    return res


def sync_transactions_for_item(item: PlaidItem) -> SyncResult:
    """
    Ejecuta /transactions/sync hasta has_more=false, guarda cursor,
    y crea alertas por ingresos/gastos nuevos.
    """
    cfg = load_plaid_config()
    client = PlaidHttpClient(cfg)

    cursor = (item.tx_cursor or "").strip() or None
    out = SyncResult(next_cursor=item.tx_cursor or "")

    while True:
        data = client.transactions_sync(access_token=item.access_token, cursor=cursor)

        added = data.get("added") or []
        modified = data.get("modified") or []
        removed = data.get("removed") or []

        next_cursor = (data.get("next_cursor") or "").strip()
        has_more = bool(data.get("has_more", False))

        with db_tx.atomic():
            chunk = _upsert_transactions(item=item, added=added, modified=modified, removed=removed)
            out.added += chunk.added
            out.modified += chunk.modified
            out.removed += chunk.removed
            out.new_income_alerts += chunk.new_income_alerts
            out.new_expense_alerts += chunk.new_expense_alerts

            if next_cursor:
                item.tx_cursor = next_cursor
                item.last_synced_at = timezone.now()
                item.save(update_fields=["tx_cursor", "last_synced_at", "updated_at"])
                out.next_cursor = next_cursor

        cursor = next_cursor or cursor

        if not has_more:
            break

    return out


def sync_transactions_for_user(user) -> Dict[str, Any]:
    """
    Sincroniza todos los PlaidItem del usuario.
    Retorna un resumen para la API.
    """
    items = list(PlaidItem.objects.filter(user=user))
    total_income_alerts = 0
    total_expense_alerts = 0
    total_added = 0
    total_modified = 0
    total_removed = 0

    for item in items:
        r = sync_transactions_for_item(item)
        total_income_alerts += r.new_income_alerts
        total_expense_alerts += r.new_expense_alerts
        total_added += r.added
        total_modified += r.modified
        total_removed += r.removed

    return {
        "synced_items": len(items),
        "added": total_added,
        "modified": total_modified,
        "removed": total_removed,
        "new_income_alerts": total_income_alerts,
        "new_expense_alerts": total_expense_alerts,
    }
