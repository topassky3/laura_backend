from django.urls import path

from .views import (
    PlaidExchangePublicTokenView,
    PlaidLinkTokenView,
    PlaidStatusView,
    PlaidDisconnectView,  # ✅ FIX: faltaba importar esta vista
)

urlpatterns = [
    path("api/plaid/link-token/", PlaidLinkTokenView.as_view(), name="plaid-link-token"),
    path("api/plaid/exchange-public-token/", PlaidExchangePublicTokenView.as_view(), name="plaid-exchange-public-token"),
    path("api/plaid/status/", PlaidStatusView.as_view(), name="plaid-status"),
    path("api/plaid/disconnect/", PlaidDisconnectView.as_view(), name="plaid-disconnect"),
]
