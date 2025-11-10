from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, MoneyTxViewSet

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"transactions", MoneyTxViewSet, basename="moneytx")

urlpatterns = [
    path("", include(router.urls)),
]
