"""
Provider Orange Money (Orange API).

En production : appels vers api.orange.com/orange-money-webpay
Sandbox : simulation locale.

Credentials attendus dans les settings :
  ORANGE_MONEY_CLIENT_ID
  ORANGE_MONEY_CLIENT_SECRET
  ORANGE_MONEY_MERCHANT_KEY
  ORANGE_MONEY_ENV   — "sandbox" | "production"
"""
import uuid

from django.conf import settings

from .base import MobileMoneyProvider, PaymentRequest, PaymentResult
from .registry import register_provider


@register_provider
class OrangeMoneyProvider(MobileMoneyProvider):

    @property
    def operator_code(self) -> str:
        return "orange"

    def _is_sandbox(self) -> bool:
        return getattr(settings, "ORANGE_MONEY_ENV", "sandbox") == "sandbox"

    def initiate(self, request: PaymentRequest) -> PaymentResult:
        if self._is_sandbox():
            return self._sandbox_initiate(request)
        return self._production_initiate(request)  # pragma: no cover

    def check_status(self, external_id: str) -> PaymentResult:
        if self._is_sandbox():
            return self._sandbox_check(external_id)
        return self._production_check(external_id)  # pragma: no cover

    # ------------------------------------------------------------------
    # Sandbox
    # ------------------------------------------------------------------

    def _sandbox_initiate(self, request: PaymentRequest) -> PaymentResult:
        ext_id = str(uuid.uuid4())
        return PaymentResult(
            success=True,
            external_id=ext_id,
            status="pending",
            raw={
                "sandbox": True,
                "operator": "orange",
                "amount": str(request.amount),
                "currency": request.currency,
                "payer": request.payer_phone,
            },
        )

    def _sandbox_check(self, external_id: str) -> PaymentResult:
        return PaymentResult(
            success=True,
            external_id=external_id,
            status="confirmed",
            raw={"sandbox": True, "operator": "orange", "id": external_id},
        )

    # ------------------------------------------------------------------
    # Production
    # ------------------------------------------------------------------

    def _production_initiate(self, request: PaymentRequest) -> PaymentResult:  # pragma: no cover
        import requests as http

        client_id = settings.ORANGE_MONEY_CLIENT_ID
        client_secret = settings.ORANGE_MONEY_CLIENT_SECRET
        merchant_key = settings.ORANGE_MONEY_MERCHANT_KEY

        # 1. Token OAuth2
        token_resp = http.post(
            "https://api.orange.com/oauth/v3/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            timeout=10,
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]

        ext_id = str(uuid.uuid4())

        # 2. Initiation du paiement Web Pay
        payload = {
            "merchant_key": merchant_key,
            "currency": request.currency,
            "order_id": ext_id,
            "amount": int(request.amount),
            "return_url": "",
            "cancel_url": "",
            "notif_url": "",
            "lang": "fr",
            "reference": request.reference,
        }
        resp = http.post(
            "https://api.orange.com/orange-money-webpay/cm/v1/webpayment",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )

        if resp.status_code == 200:
            data = resp.json()
            return PaymentResult(
                success=True,
                external_id=data.get("pay_token", ext_id),
                status="pending",
                raw=data,
            )
        return PaymentResult(
            success=False, external_id=ext_id, status="failed",
            failure_reason=resp.text, raw={},
        )

    def _production_check(self, external_id: str) -> PaymentResult:  # pragma: no cover
        import requests as http

        client_id = settings.ORANGE_MONEY_CLIENT_ID
        client_secret = settings.ORANGE_MONEY_CLIENT_SECRET

        token_resp = http.post(
            "https://api.orange.com/oauth/v3/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            timeout=10,
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]

        resp = http.get(
            f"https://api.orange.com/orange-money-webpay/cm/v1/transactionstatus/{external_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        status_map = {"SUCCESS": "confirmed", "FAILED": "failed", "PENDING": "pending"}
        om_status = status_map.get(data.get("status", "").upper(), "pending")

        return PaymentResult(
            success=om_status != "failed",
            external_id=external_id,
            status=om_status,
            failure_reason=data.get("message", "") if om_status == "failed" else "",
            raw=data,
        )
