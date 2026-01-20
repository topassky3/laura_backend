import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


PLAID_ENV_URLS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}


class PlaidApiError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, details: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


def _looks_like_placeholder(v: str) -> bool:
    s = (v or "").strip()
    if not s:
        return True
    low = s.lower()
    if low in {"xxxx", "yyyy", "changeme", "your_client_id", "your_secret"}:
        return True
    if len(s) <= 12 and (set(low) <= {"x"} or set(low) <= {"y"}):
        return True
    if "placeholder" in low or "example" in low:
        return True
    return False


def _validate_plaid_id(name: str, value: str) -> None:
    v = (value or "").strip()
    if _looks_like_placeholder(v):
        raise PlaidApiError(
            f"Config Plaid inválida: {name} parece placeholder o vacío. "
            f"Ve a Plaid Dashboard → Developers → Keys (Sandbox) y pega el valor real.",
            status_code=500,
        )
    if len(v) < 8:
        raise PlaidApiError(
            f"Config Plaid inválida: {name} es demasiado corto.",
            status_code=500,
        )


@dataclass(frozen=True)
class PlaidConfig:
    env: str
    client_id: str
    secret: str
    client_name: str
    language: str
    country_codes: list[str]
    products: list[str]
    webhook: str
    redirect_uri: str
    android_package_name: str
    tx_days_requested: int

    @property
    def base_url(self) -> str:
        return PLAID_ENV_URLS.get(self.env, PLAID_ENV_URLS["sandbox"])


def load_plaid_config() -> PlaidConfig:
    env = os.getenv("PLAID_ENV", "sandbox").strip().lower()
    if env not in PLAID_ENV_URLS:
        env = "sandbox"

    client_id = os.getenv("PLAID_CLIENT_ID", "").strip()
    secret = os.getenv("PLAID_SECRET", "").strip()

    _validate_plaid_id("PLAID_CLIENT_ID", client_id)
    _validate_plaid_id("PLAID_SECRET", secret)

    products = [p.strip() for p in os.getenv("PLAID_PRODUCTS", "transactions").split(",") if p.strip()]
    country_codes = [c.strip().upper() for c in os.getenv("PLAID_COUNTRY_CODES", "US").split(",") if c.strip()]

    return PlaidConfig(
        env=env,
        client_id=client_id,
        secret=secret,
        client_name=os.getenv("PLAID_CLIENT_NAME", "Tu App").strip() or "Tu App",
        language=os.getenv("PLAID_LANGUAGE", "en").strip() or "en",
        country_codes=country_codes or ["US"],
        products=products or ["transactions"],
        webhook=os.getenv("PLAID_WEBHOOK", "").strip(),
        redirect_uri=os.getenv("PLAID_REDIRECT_URI", "").strip(),
        android_package_name=os.getenv("PLAID_ANDROID_PACKAGE_NAME", "").strip(),
        tx_days_requested=int(os.getenv("PLAID_TX_DAYS_REQUESTED", "90")),
    )


class PlaidHttpClient:
    def __init__(self, cfg: PlaidConfig):
        self.cfg = cfg

    def _headers(self) -> Dict[str, str]:
        # Ok enviar también en headers; igualmente mandamos en body por compatibilidad.
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "PLAID-CLIENT-ID": self.cfg.client_id,
            "PLAID-SECRET": self.cfg.secret,
        }

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.cfg.base_url}{path}"

        merged_payload = {
            "client_id": self.cfg.client_id,
            "secret": self.cfg.secret,
            **payload,
        }

        res = requests.post(url, json=merged_payload, headers=self._headers(), timeout=25)

        try:
            data = res.json()
        except Exception:
            raise PlaidApiError(f"Respuesta no-JSON de Plaid ({res.status_code}): {res.text}", status_code=502)

        if res.status_code < 200 or res.status_code >= 300:
            msg = data.get("error_message") or data.get("display_message") or "Error Plaid"
            raise PlaidApiError(msg, status_code=res.status_code, details=data)

        return data

    def create_link_token(
        self,
        *,
        client_user_id: str,
        android_package_name: str = "",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user": {"client_user_id": client_user_id},
            "client_name": self.cfg.client_name,
            "products": self.cfg.products,
            "language": self.cfg.language,
            "country_codes": self.cfg.country_codes,
        }

        if "transactions" in [p.lower() for p in self.cfg.products]:
            payload["transactions"] = {"days_requested": self.cfg.tx_days_requested}

        if self.cfg.webhook:
            payload["webhook"] = self.cfg.webhook

        if self.cfg.redirect_uri:
            payload["redirect_uri"] = self.cfg.redirect_uri

        # ✅ android_package_name (preferimos el que llega del móvil; si no, usamos el del .env)
        pkg = (android_package_name or "").strip() or (self.cfg.android_package_name or "").strip()
        if pkg:
            payload["android_package_name"] = pkg

        return self._post("/link/token/create", payload)

    def exchange_public_token(self, *, public_token: str) -> Dict[str, Any]:
        return self._post("/item/public_token/exchange", {"public_token": public_token})

    # ✅ NUEVO: sync transacciones incremental
    def transactions_sync(
        self,
        *,
        access_token: str,
        cursor: str | None = None,
        count: int = 500,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "access_token": access_token,
            "count": count,
        }
        if cursor:
            payload["cursor"] = cursor
        return self._post("/transactions/sync", payload)

    # ✅ NUEVO: revocar acceso Plaid al desconectar
    def item_remove(self, *, access_token: str) -> Dict[str, Any]:
        return self._post("/item/remove", {"access_token": access_token})

    # ✅ SANDBOX ONLY: crear transacciones de prueba
    def sandbox_transactions_create(
            self,
            *,
            access_token: str,
            transactions: list[dict],
    ) -> Dict[str, Any]:
        return self._post(
            "/sandbox/transactions/create",
            {
                "access_token": access_token,
                "transactions": transactions,
            },
        )
