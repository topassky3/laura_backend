# finance/models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

POCKET_TYPES = (
    ("ingreso", "Ingreso"),
    ("gasto", "Gasto"),
    ("ahorro", "Ahorro"),
    ("inversion", "Inversión"),
)


class Category(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    pocket_type = models.CharField(max_length=10, choices=POCKET_TYPES)
    name = models.CharField(max_length=48)
    icon_name = models.CharField(max_length=32, default="label")
    color_hex = models.CharField(
        max_length=9,
        default="#64748B",  # #RRGGBB o #AARRGGBB
    )
    order = models.PositiveSmallIntegerField(default=0)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("user", "pocket_type", "name"),)
        ordering = ["pocket_type", "order", "name"]

    def __str__(self) -> str:
        return f"{self.user_id} · {self.pocket_type} · {self.name}"


class MoneyTx(models.Model):
    TYPE_CHOICES = (("ingreso", "Ingreso"), ("gasto", "Gasto"))
    PAYMENT_CHOICES = (("debito", "Débito"), ("credito", "Crédito"))

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="money_txs",
    )

    # Bolsillo real de la transacción (clasificación correcta)
    pocket_type = models.CharField(
        max_length=10,
        choices=POCKET_TYPES,
        default="gasto",
    )

    # 'type' se usa solo para la dirección visual (flechas/colores en la UI)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)

    # Relación opcional con Category para consistencia; y nombre plano para compatibilidad
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="txs",
    )
    category_name = models.CharField(max_length=48)

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="COP")
    date = models.DateTimeField()
    payment = models.CharField(
        max_length=10,
        choices=PAYMENT_CHOICES,
        default="debito",
    )
    is_fixed = models.BooleanField(default=False)
    note = models.CharField(max_length=240, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["user", "pocket_type", "category_name"]),
            models.Index(fields=["user", "date"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.user_id} · {self.pocket_type}/{self.type} · "
            f"{self.category_name} · {self.amount} {self.currency}"
        )

    @property
    def pocket_sign(self) -> int:
        # Para flujo de caja neto: ingreso = +, resto = -
        return 1 if self.pocket_type == "ingreso" else -1
