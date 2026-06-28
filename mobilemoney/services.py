"""
Service Mobile Money — orchestration des transactions (F-17 à F-19).
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from sales.models import Payment, Sale

from .models import MobileMoneyTransaction
from .providers import PaymentRequest, get_provider


class MobileMoneyService:

    @staticmethod
    @transaction.atomic
    def initiate(
        *,
        tenant,
        sale: Sale,
        operator: str,
        payer_phone: str,
        amount: Decimal,
    ) -> MobileMoneyTransaction:
        """
        Initie une transaction Mobile Money pour une vente.

        Crée le MobileMoneyTransaction en base, appelle le provider,
        met à jour le statut. Retourne la transaction pour que la vue
        puisse suivre son état (F-19).
        """
        currency = tenant.currency
        reference = sale.reference or str(sale.id)[:8].upper()

        momo_tx = MobileMoneyTransaction.objects.create(
            tenant=tenant,
            sale=sale,
            operator=operator,
            payer_phone=payer_phone,
            amount=amount,
            currency=currency,
            reference=reference,
            status=MobileMoneyTransaction.Status.INITIATED,
        )

        provider = get_provider(operator)
        result = provider.initiate(PaymentRequest(
            payer_phone=payer_phone,
            amount=amount,
            currency=currency,
            reference=reference,
            description=f"Paiement vente {reference}",
        ))

        momo_tx.external_id = result.external_id
        momo_tx.provider_response = result.raw
        momo_tx.status_updated_at = timezone.now()

        if result.success:
            momo_tx.status = MobileMoneyTransaction.Status.PENDING
        else:
            momo_tx.status = MobileMoneyTransaction.Status.FAILED
            momo_tx.failure_reason = result.failure_reason

        momo_tx.save(update_fields=[
            "external_id", "provider_response", "status",
            "failure_reason", "status_updated_at",
        ])
        return momo_tx

    @staticmethod
    @transaction.atomic
    def check_and_update(momo_tx: MobileMoneyTransaction, *, recorded_by) -> MobileMoneyTransaction:
        """
        Interroge l'opérateur et met à jour le statut de la transaction (F-19).

        Si la transaction passe en 'confirmed' :
          - Crée le Payment Django correspondant
          - Lie le Payment à la transaction
        """
        if momo_tx.status in (
            MobileMoneyTransaction.Status.CONFIRMED,
            MobileMoneyTransaction.Status.FAILED,
        ):
            return momo_tx  # Terminal — pas la peine d'interroger l'opérateur

        provider = get_provider(momo_tx.operator)
        result = provider.check_status(momo_tx.external_id)

        momo_tx.provider_response = result.raw
        momo_tx.status_updated_at = timezone.now()

        if result.status == "confirmed":
            momo_tx.status = MobileMoneyTransaction.Status.CONFIRMED

            # Crée le Payment Django si pas encore fait (F-18 — rapprochement)
            if momo_tx.payment_id is None and momo_tx.sale_id:
                method_map = {
                    MobileMoneyTransaction.Operator.MTN: Payment.Method.MOMO,
                    MobileMoneyTransaction.Operator.ORANGE: Payment.Method.ORANGE_MONEY,
                }
                payment = Payment.objects.create(
                    tenant=momo_tx.tenant,
                    sale=momo_tx.sale,
                    method=method_map.get(momo_tx.operator, Payment.Method.MOMO),
                    amount=momo_tx.amount,
                    status=Payment.Status.CONFIRMED,
                    recorded_by=recorded_by,
                )
                momo_tx.payment = payment

        elif result.status == "failed":
            momo_tx.status = MobileMoneyTransaction.Status.FAILED
            momo_tx.failure_reason = result.failure_reason

        momo_tx.save(update_fields=[
            "status", "provider_response", "failure_reason",
            "payment", "status_updated_at",
        ])
        return momo_tx
