from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from .models import Category
from .serializers import CategorySerializer

DEFAULTS = {
    "ingreso":   [("Salario", "wallet", "#22C55E"), ("Freelance", "wallet", "#22C55E"), ("Ventas", "wallet", "#22C55E")],
    "gasto":     [("Comida", "restaurant", "#EF4444"), ("Transporte", "directions_bus", "#EF4444"), ("Servicios", "bolt", "#EF4444")],
    "ahorro":    [("Fondo emergencia", "savings", "#4DB6AC"), ("Viaje", "flight", "#4DB6AC")],
    "inversion": [("ETF", "trending_up", "#7E57C2"), ("Cripto", "currency_bitcoin", "#7E57C2")],
}

def ensure_defaults(user, pocket_type=None):
    """
    Si el usuario no tiene categorías (o no tiene para un pocket_type), crear defaults.
    """
    created = []
    with transaction.atomic():
        if pocket_type:
            qs = Category.objects.filter(user=user, pocket_type=pocket_type)
            if not qs.exists():
                rows = DEFAULTS.get(pocket_type, [])
                for i, (name, icon, color) in enumerate(rows):
                    created.append(Category.objects.create(
                        user=user, pocket_type=pocket_type, name=name,
                        icon_name=icon, color_hex=color, order=i, is_default=True
                    ))
        else:
            if not Category.objects.filter(user=user).exists():
                for ptype, rows in DEFAULTS.items():
                    for i, (name, icon, color) in enumerate(rows):
                        created.append(Category.objects.create(
                            user=user, pocket_type=ptype, name=name,
                            icon_name=icon, color_hex=color, order=i, is_default=True
                        ))
    return created

class CategoryViewSet(viewsets.ModelViewSet):
    """
    /api/fin/categories/?pocket_type=gasto
    """
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
        # Auto-seed si no hay categorías para el user
        ensure_defaults(request.user, pocket_type=ptype)
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        # forzar orden al final
        user = self.request.user
        ptype = serializer.validated_data["pocket_type"]
        last = Category.objects.filter(user=user, pocket_type=ptype).order_by("-order").first()
        next_order = (last.order + 1) if last else 0
        serializer.save(order=next_order)

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        """
        Body: [{"id": 12, "order": 0}, ...]
        """
        user = request.user
        items = request.data if isinstance(request.data, list) else []
        with transaction.atomic():
            for it in items:
                Category.objects.filter(id=it.get("id"), user=user).update(order=it.get("order", 0))
        return Response({"detail": "ok"})
