"""
App `mobilemoney` — Suivi des transactions Mobile Money (F-17 à F-19).

Architecture modulaire : chaque opérateur est un Provider indépendant.
Ce modèle est le journal de chaque tentative de paiement externe.
"""
from django.db import models

from kenpro_store.db import TenantOwnedModel


class MobileMoneyTransaction(TenantOwnedModel):
    """
    Représente une tentative de paiement via un opérateur Mobile Money.

    Cycle de vie :
      initiated → pending (demande envoyée à l'opérateur)
                → confirmed (opérateur confirme)
                → failed    (opérateur rejette ou timeout)

    `payment` est nullable : on initie la transaction avant que le Payment
    Django soit créé. Le Payment est créé seulement à la confirmation.
    """

    class Operator(models.TextChoices):
        MTN = "mtn", "MTN MoMo"
        ORANGE = "orange", "Orange Money"
        WAVE = "wave", "Wave"

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiée"
        PENDING = "pending", "En attente opérateur"
        CONFIRMED = "confirmed", "Confirmée"
        FAILED = "failed", "Échouée"

    # Lien vers le Payment Django — créé à la confirmation (F-18)
    payment = models.OneToOneField(
        "sales.Payment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="momo_transaction",
    )
    # Vente concernée (rapprochement F-18)
    sale = models.ForeignKey(
        "sales.Sale",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="momo_transactions",
    )
    operator = models.CharField(max_length=20, choices=Operator.choices)
    payer_phone = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="XAF")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INITIATED,
    )
    # Référence courte affichée au vendeur
    reference = models.CharField(max_length=64, blank=True)
    # Identifiant renvoyé par l'opérateur
    external_id = models.CharField(max_length=255, blank=True)
    # Payload brut retourné par l'opérateur (audit)
    provider_response = models.JSONField(default=dict, blank=True)
    status_updated_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = "Transaction Mobile Money"
        verbose_name_plural = "Transactions Mobile Money"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return (
            f"{self.get_operator_display()} {self.amount} {self.currency} "
            f"— {self.payer_phone} ({self.get_status_display()})"
        )
