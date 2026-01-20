from django.urls import path

from .views import (
    BankAlertsAckView,
    BankAlertsUnreadView,
    PlaidDisconnectView,
    PlaidExchangePublicTokenView,
    PlaidLinkTokenView,
    PlaidStatusView,
    PlaidSyncNowView,
)

urlpatterns = [
    path("api/plaid/link-token/", PlaidLinkTokenView.as_view(), name="plaid-link-token"),
    path("api/plaid/exchange-public-token/", PlaidExchangePublicTokenView.as_view(), name="plaid-exchange-public-token"),
    path("api/plaid/status/", PlaidStatusView.as_view(), name="plaid-status"),
    path("api/plaid/disconnect/", PlaidDisconnectView.as_view(), name="plaid-disconnect"),
    # ✅ NUEVO
    path("api/plaid/sync-now/", PlaidSyncNowView.as_view(), name="plaid-sync-now"),
    path("api/alerts/unread/", BankAlertsUnreadView.as_view(), name="alerts-unread"),
    path("api/alerts/ack/", BankAlertsAckView.as_view(), name="alerts-ack"),
]
