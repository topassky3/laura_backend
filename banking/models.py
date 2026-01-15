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
    Cuentas seleccionadas/retornadas por Link (metadata). Esto NO es obligatorio para el MVP,
    pero ayuda para mapear transacciones por cuenta.
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
        return f"PlaidAccount(item={self.item_id}, account_id={self.account_id})"
