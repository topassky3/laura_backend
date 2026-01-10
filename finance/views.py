# finance/views.py
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.db.models import Sum

from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Category, MoneyTx
from .serializers import CategorySerializer, MoneyTxSerializer

DEFAULTS = {
    "ingreso": [
        ("Salario", "wallet", "#22C55E"),
        ("Freelance", "wallet", "#22C55E"),
        ("Ventas", "wallet", "#22C55E"),
    ],
    "gasto": [
        ("Comida", "restaurant", "#EF4444"),
        ("Transporte", "directions_bus", "#EF4444"),
        ("Servicios", "bolt", "#EF4444"),
    ],
    "ahorro": [
        ("Fondo emergencia", "savings", "#4DB6AC"),
        ("Viaje", "flight", "#4DB6AC"),
    ],
    "inversion": [
        ("ETF", "trending_up", "#7E57C2"),
        ("Cripto", "currency_bitcoin", "#7E57C2"),
    ],
}


def ensure_defaults(user, pocket_type: str | None = None):
    created = []
    with transaction.atomic():
        if pocket_type:
            qs = Category.objects.filter(user=user, pocket_type=pocket_type)
            if not qs.exists():
                rows = DEFAULTS.get(pocket_type, [])
                for i, (name, icon, color) in enumerate(rows):
                    created.append(
                        Category.objects.create(
                            user=user,
                            pocket_type=pocket_type,
                            name=name,
                            icon_name=icon,
                            color_hex=color,
                            order=i,
                            is_default=True,
                        )
                    )
        else:
            if not Category.objects.filter(user=user).exists():
                for ptype, rows in DEFAULTS.items():
                    for i, (name, icon, color) in enumerate(rows):
                        created.append(
                            Category.objects.create(
                                user=user,
                                pocket_type=ptype,
                                name=name,
                                icon_name=icon,
                                color_hex=color,
                                order=i,
                                is_default=True,
                            )
                        )
    return created


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Category.objects.filter(user=user)

        ptype = self.request.query_params.get("pocket_type")
        if ptype:
            qs = qs.filter(pocket_type=ptype)

        return qs

    def list(self, request, *args, **kwargs):
        ptype = request.query_params.get("pocket_type")
        ensure_defaults(request.user, pocket_type=ptype)
        return super().list(request, *args, **kwargs)


class MoneyTxViewSet(viewsets.ModelViewSet):
    serializer_class = MoneyTxSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _apply_time_filters(self, qs):
        """
        Aplica filtros de tiempo si vienen en query params:
        - month=YYYY-MM
        - start/end en ISO (incluye soporte "Z")
        Si no vienen, NO filtra (lifetime).
        """
        month = self.request.query_params.get("month")
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        tz = timezone.get_current_timezone()

        if month:
            try:
                year, mon = [int(x) for x in month.split("-")]
                start_dt = timezone.make_aware(datetime(year, mon, 1, 0, 0, 0), tz)
                if mon == 12:
                    end_dt = timezone.make_aware(datetime(year + 1, 1, 1, 0, 0, 0), tz)
                else:
                    end_dt = timezone.make_aware(datetime(year, mon + 1, 1, 0, 0, 0), tz)
                qs = qs.filter(date__gte=start_dt, date__lt=end_dt)
            except Exception:
                # Silencioso por UX: si mandan month mal formado, no filtramos
                pass

        if start and end:
            try:
                if "Z" in start:
                    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                else:
                    start_dt = timezone.make_aware(datetime.fromisoformat(start), tz)

                if "Z" in end:
                    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                else:
                    end_dt = timezone.make_aware(datetime.fromisoformat(end), tz)

                qs = qs.filter(date__gte=start_dt, date__lt=end_dt)
            except Exception:
                # Silencioso: si vienen fechas mal, no filtramos
                pass

        return qs

    def get_queryset(self):
        user = self.request.user
        qs = MoneyTx.objects.filter(user=user)

        qs = self._apply_time_filters(qs)

        pocket = (
            self.request.query_params.get("pocket_type")
            or self.request.query_params.get("pocket")
        )
        if pocket:
            qs = qs.filter(pocket_type=pocket)

        # 👇 filtro por nombre de categoría
        category_name = (
            self.request.query_params.get("category_name")
            or self.request.query_params.get("category")
        )
        if category_name:
            qs = qs.filter(category_name=category_name)

        return qs.order_by("-date", "-id")

    @action(detail=False, methods=["get"], url_path="category-totals")
    def category_totals(self, request):
        """
        Totales por categoría.

        - Requiere: pocket_type (o pocket)
        - Opcional: month=YYYY-MM o start/end
        - Si NO mandas month/start/end => LIFETIME (todo el tiempo)
        """
        pocket_type = (
            request.query_params.get("pocket_type")
            or request.query_params.get("pocket")
        )
        if not pocket_type:
            raise ValidationError({"pocket_type": "Este parámetro es requerido."})

        qs = MoneyTx.objects.filter(user=request.user, pocket_type=pocket_type)
        qs = self._apply_time_filters(qs)

        # Opcional: por moneda (si lo necesitas)
        currency = request.query_params.get("currency")
        if currency:
            qs = qs.filter(currency=(currency or "").upper().strip())

        rows = (
            qs.order_by()  # 🔥 importante: limpia ordering antes de agrupar
            .values("category_name", "pocket_type")
            .annotate(total_amount=Sum("amount"))
            .order_by("-total_amount", "category_name")
        )

        return Response(list(rows))
