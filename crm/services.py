"""
Couche service de l'app `crm`.
"""
from django.db import transaction
from django.db.models import F

from .models import Customer, DebtMovement


class DebtService:
    """
    Gère les mouvements de dette client.
    Toutes les écritures passent par ici — jamais directement via l'ORM.
    """

    @staticmethod
    @transaction.atomic
    def charge(
        customer: Customer,
        amount,
        *,
        reference: str = "",
        note: str = "",
        recorded_by,
    ) -> DebtMovement:
        """Impute une vente à crédit : augmente la dette du client."""
        if amount <= 0:
            raise ValueError("Le montant d'une charge doit être positif.")

        movement = DebtMovement.objects.create(
            tenant=customer.tenant,
            customer=customer,
            type=DebtMovement.Type.SALE,
            amount=amount,
            reference=reference,
            note=note,
            recorded_by=recorded_by,
        )
        Customer.objects.filter(pk=customer.pk).update(debt_balance=F("debt_balance") + amount)
        customer.refresh_from_db(fields=["debt_balance"])
        return movement

    @staticmethod
    @transaction.atomic
    def repay(
        customer: Customer,
        amount,
        *,
        reference: str = "",
        note: str = "",
        recorded_by,
    ) -> DebtMovement:
        """Enregistre un remboursement : diminue la dette du client."""
        if amount <= 0:
            raise ValueError("Le montant d'un remboursement doit être positif.")

        movement = DebtMovement.objects.create(
            tenant=customer.tenant,
            customer=customer,
            type=DebtMovement.Type.REPAYMENT,
            amount=-amount,
            reference=reference,
            note=note,
            recorded_by=recorded_by,
        )
        Customer.objects.filter(pk=customer.pk).update(debt_balance=F("debt_balance") - amount)
        customer.refresh_from_db(fields=["debt_balance"])
        return movement

    @staticmethod
    @transaction.atomic
    def adjust(
        customer: Customer,
        amount,
        *,
        note: str = "",
        recorded_by,
    ) -> DebtMovement:
        """Ajustement libre (positif ou négatif) avec note obligatoire."""
        if not note:
            raise ValueError("Un ajustement doit être accompagné d'une note.")

        movement = DebtMovement.objects.create(
            tenant=customer.tenant,
            customer=customer,
            type=DebtMovement.Type.ADJUSTMENT,
            amount=amount,
            note=note,
            recorded_by=recorded_by,
        )
        Customer.objects.filter(pk=customer.pk).update(debt_balance=F("debt_balance") + amount)
        customer.refresh_from_db(fields=["debt_balance"])
        return movement

    @staticmethod
    def history(customer: Customer):
        return DebtMovement.objects.filter(customer=customer).order_by("created_at")
