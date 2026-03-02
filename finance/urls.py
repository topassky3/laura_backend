# finance/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, MoneyTxViewSet, FinancePreferencesView

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"transactions", MoneyTxViewSet, basename="moneytx")

urlpatterns = [
    path("", include(router.urls)),
    # ✅ NUEVO
    path("preferences/", FinancePreferencesView.as_view(), name="finance-preferences"),
]
