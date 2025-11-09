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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="categories")
    pocket_type = models.CharField(max_length=10, choices=POCKET_TYPES)
    name = models.CharField(max_length=48)
    icon_name = models.CharField(max_length=32, default="label")
    color_hex = models.CharField(max_length=9, default="#64748B")  # #RRGGBB o #AARRGGBB
    order = models.PositiveSmallIntegerField(default=0)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("user", "pocket_type", "name"),)
        ordering = ["pocket_type", "order", "name"]

    def __str__(self):
        return f"{self.user_id} · {self.pocket_type} · {self.name}"
