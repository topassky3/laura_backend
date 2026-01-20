from __future__ import annotations

from django.conf import settings
from django.db import models


class PlaidItem(models.Model):
    """
    Guarda el access_token (server-side) y el item_id asociado a un usuario.
    Nunca se debe enviar access_token al cliente.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="plaid_items")

    item_id = models.CharField(max_length=128, unique=True)
    access_token = models.TextField()

    institution_id = models.CharField(max_length=128, blank=True, default="")
    institution_name = models.CharField(max_length=255, blank=True, default="")

    # ✅ NUEVO: cursor para /transactions/sync
    tx_cursor = models.CharField(max_length=512, blank=True, default="")
    last_synced_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "item_id"]),
        ]

    def __str__(self) -> str:
        return f"PlaidItem(user={self.user_id}, item_id={self.item_id})"


class PlaidAccount(models.Model):
    """
    Cuentas seleccionadas/retornadas por Link (metadata).
    """
    item = models.ForeignKey(PlaidItem, on_delete=models.CASCADE, related_name="accounts")

    account_id = models.CharField(max_length=128)
    mask = models.CharField(max_length=16, blank=True, default="")
    name = models.CharField(max_length=255, blank=True, default="")
    type = models.CharField(max_length=64, blank=True, default="")
    subtype = models.CharField(max_length=64, blank=True, default="")
    verification_status = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        unique_together = (("item", "account_id"),)
        indexes = [
            models.Index(fields=["item", "account_id"]),
        ]

    def __str__(self) -> str:
        return f"PlaidAccount(item_db_id={self.item_id}, account_id={self.account_id})"


class PlaidTransaction(models.Model):
    """
    Transacciones sincronizadas por /transactions/sync.
    Guardamos raw para depurar/categorizar en el futuro.
    """
    item = models.ForeignKey(PlaidItem, on_delete=models.CASCADE, related_name="transactions")

    transaction_id = models.CharField(max_length=128, unique=True)
    account_id = models.CharField(max_length=128, blank=True, default="")

    name = models.CharField(max_length=512, blank=True, default="")
    merchant_name = models.CharField(max_length=255, blank=True, default="")

    # ⚠️ Plaid: CREDIT suele venir negativo, DEBIT positivo (según docs de Plaid) :contentReference[oaicite:1]{index=1}
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    iso_currency_code = models.CharField(max_length=8, blank=True, default="")
    unofficial_currency_code = models.CharField(max_length=16, blank=True, default="")

    date = models.DateField(null=True, blank=True)
    authorized_date = models.DateField(null=True, blank=True)

    pending = models.BooleanField(default=False)

    # Si viene (depende del producto / versión): CREDIT/DEBIT/MEMO
    transaction_type = models.CharField(max_length=16, blank=True, default="")

    raw = models.JSONField(blank=True, default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["item", "account_id"]),
            models.Index(fields=["item", "date"]),
        ]

    def __str__(self) -> str:
        return f"PlaidTransaction(item={self.item_id}, tx={self.transaction_id})"


class BankAlert(models.Model):
    """
    Alertas por ingresos detectados.
    Se consumen por la app móvil y se marcan como 'seen' cuando el cliente hace ACK.
    """
    KIND_INCOME = "income"
    KIND_CHOICES = [
        (KIND_INCOME, "Income"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bank_alerts")
    item = models.ForeignKey(PlaidItem, on_delete=models.CASCADE, related_name="alerts")

    transaction = models.OneToOneField(
        PlaidTransaction,
        on_delete=models.CASCADE,
        related_name="alert",
        null=True,
        blank=True,
    )

    kind = models.CharField(max_length=32, choices=KIND_CHOICES, default=KIND_INCOME)

    title = models.CharField(max_length=255)
    message = models.TextField(blank=True, default="")

    # Guardamos el valor como positivo para UI (abs)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, blank=True, default="")

    # null => no vista aún
    seen_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "seen_at", "created_at"]),
            models.Index(fields=["item", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"BankAlert(user={self.user_id}, kind={self.kind}, id={self.id})"
