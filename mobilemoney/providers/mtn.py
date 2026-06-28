"""
Provider MTN MoMo (Collections API).

En production : appels vers api.mtn.com/collection/v1_0/requesttopay
Sandbox : simulation locale contrôlée par MTN_MOMO_SANDBOX=true.

Credentials attendus dans les settings :
  MTN_MOMO_SUBSCRIPTION_KEY   — clé d'abonnement API
  MTN_MOMO_API_USER           — UUID créé lors de l'onboarding sandbox
  MTN_MOMO_API_KEY            — clé générée pour cet API user
  MTN_MOMO_ENV                — "sandbox" | "production"
  MTN_MOMO_CURRENCY           — devise (ex. "XAF", "EUR")
"""
import uuid

from django.conf import settings

from .base import MobileMoneyProvider, PaymentRequest, PaymentResult
from .registry import register_provider


@register_provider
class MTNMoMoProvider(MobileMoneyProvider):

    @property
    def operator_code(self) -> str:
        return "mtn"

    def _is_sandbox(self) -> bool:
        return getattr(settings, "MTN_MOMO_ENV", "sandbox") == "sandbox"

    def initiate(self, request: PaymentRequest) -> PaymentResult:
        if self._is_sandbox():
            return self._sandbox_initiate(request)
        return self._production_initiate(request)  # pragma: no cover

    def check_status(self, external_id: str) -> PaymentResult:
        if self._is_sandbox():
            return self._sandbox_check(external_id)
        return self._production_check(external_id)  # pragma: no cover

    # ------------------------------------------------------------------
    # Sandbox — simule le flow sans appel réseau réel
    # ------------------------------------------------------------------

    def _sandbox_initiate(self, request: PaymentRequest) -> PaymentResult:
        """
        Sandbox MTN : génère un external_id local et retourne status=pending.
        En vrai sandbox MTN, on ferait un POST /requesttopay puis le client
        confirme sur son téléphone → webhook ou polling.
        """
        ext_id = str(uuid.uuid4())
        return PaymentResult(
            success=True,
            external_id=ext_id,
            status="pending",
            raw={
                "sandbox": True,
                "operator": "mtn",
                "amount": str(request.amount),
                "currency": request.currency,
                "payer": request.payer_phone,
            },
        )

    def _sandbox_check(self, external_id: str) -> PaymentResult:
        """
        Sandbox : simule une confirmation systématique après initiation.
        En production, on ferait GET /requesttopay/{external_id}.
        """
        return PaymentResult(
            success=True,
            external_id=external_id,
            status="confirmed",
            raw={"sandbox": True, "operator": "mtn", "externalId": external_id},
        )

    # ------------------------------------------------------------------
    # Production — à câbler avec les vrais credentials MTN
    # ------------------------------------------------------------------

    def _production_initiate(self, request: PaymentRequest) -> PaymentResult:  # pragma: no cover
        """
        Production MTN MoMo Collections API.
        Nécessite : MTN_MOMO_SUBSCRIPTION_KEY, MTN_MOMO_API_USER, MTN_MOMO_API_KEY.
        """
        import requests as http

        sub_key = settings.MTN_MOMO_SUBSCRIPTION_KEY
        api_user = settings.MTN_MOMO_API_USER
        api_key = settings.MTN_MOMO_API_KEY
        base_url = "https://proxy.momoapi.mtn.com"

        # 1. Obtenir un token Bearer
        token_resp = http.post(
            f"{base_url}/collection/token/",
            auth=(api_user, api_key),
            headers={"Ocp-Apim-Subscription-Key": sub_key},
            timeout=10,
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]

        ext_id = str(uuid.uuid4())

        # 2. Initier le débit (requesttopay)
        payload = {
            "amount": str(request.amount),
            "currency": request.currency,
            "externalId": ext_id,
            "payer": {"partyIdType": "MSISDN", "partyId": request.payer_phone.lstrip("+")},
            "payerMessage": request.description or request.reference,
            "payeeNote": request.reference,
        }
        resp = http.post(
            f"{base_url}/collection/v1_0/requesttopay",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Ocp-Apim-Subscription-Key": sub_key,
                "X-Reference-Id": ext_id,
                "X-Target-Environment": "production",
                "Content-Type": "application/json",
            },
            timeout=15,
        )

        if resp.status_code == 202:
            return PaymentResult(success=True, external_id=ext_id, status="pending", raw={})
        return PaymentResult(
            success=False,
            external_id=ext_id,
            status="failed",
            failure_reason=resp.text,
            raw=resp.json() if resp.content else {},
        )

    def _production_check(self, external_id: str) -> PaymentResult:  # pragma: no cover
        import requests as http

        sub_key = settings.MTN_MOMO_SUBSCRIPTION_KEY
        api_user = settings.MTN_MOMO_API_USER
        api_key = settings.MTN_MOMO_API_KEY
        base_url = "https://proxy.momoapi.mtn.com"

        token_resp = http.post(
            f"{base_url}/collection/token/",
            auth=(api_user, api_key),
            headers={"Ocp-Apim-Subscription-Key": sub_key},
            timeout=10,
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]

        resp = http.get(
            f"{base_url}/collection/v1_0/requesttopay/{external_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Ocp-Apim-Subscription-Key": sub_key,
                "X-Target-Environment": "production",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        mtn_status = data.get("status", "").upper()
        if mtn_status == "SUCCESSFUL":
            return PaymentResult(success=True, external_id=external_id, status="confirmed", raw=data)
        if mtn_status == "FAILED":
            return PaymentResult(
                success=False, external_id=external_id, status="failed",
                failure_reason=data.get("reason", ""), raw=data,
            )
        return PaymentResult(success=True, external_id=external_id, status="pending", raw=data)
