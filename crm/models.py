"""
App `crm` — Gestion de la relation client de KENPRO.

Modèles : Customer, DebtMovement.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from kenpro_store.db import TenantOwnedModel

User = settings.AUTH_USER_MODEL


class Customer(TenantOwnedModel):
    """
    Client de KENPRO : particulier ou entreprise.

    Un client « express » est créé à la volée avec uniquement un numéro de
    téléphone (lors d'une vente rapide au comptoir). Les champs non obligatoires
    sont complétés ulterieurement.
    """

    # --- Choix -----------------------------------------------------------

    class Type(models.TextChoices):
        INDIVIDUAL = "individual", "Particulier"
        BUSINESS = "business", "Entreprise"

    class TrustLevel(models.TextChoices):
        NEW = "new", "Nouveau"
        RELIABLE = "reliable", "Fiable"
        AT_RISK = "at_risk", "À risque"

    class PricingTier(models.TextChoices):
        RETAIL = "retail", "Détail (grand public)"
        RESELLER = "reseller", "Petit revendeur"
        WHOLESALE = "wholesale", "Grossiste"

    # --- Champs ----------------------------------------------------------

    # Nom complet (particulier) ou raison sociale (entreprise)
    name = models.CharField(max_length=255, verbose_name="Nom / Raison sociale")

    # Numéro de téléphone au format E.164 — contact principal, identifiant de facto
    phone = models.CharField(max_length=20, verbose_name="Téléphone (E.164)")

    # Adresse e-mail facultative
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="E-mail",
    )

    # Catégorie du client
    type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.INDIVIDUAL,
        verbose_name="Type de client",
    )

    # Segment tarifaire — détermine le prix par défaut proposé lors d'une vente.
    pricing_tier = models.CharField(
        max_length=20,
        choices=PricingTier.choices,
        default=PricingTier.RETAIL,
        verbose_name="Segment tarifaire",
    )

    # Numéro d'Identifiant Unique fiscal (B2B uniquement)
    niu = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="NIU",
        help_text="Numéro d'Identifiant Unique fiscal (clients entreprises).",
    )

    # Niveau de confiance — le calcul détaillé (historique de paiement, etc.)
    # sera implémenté dans un service dédié ultérieurement.
    trust_level = models.CharField(
        max_length=20,
        choices=TrustLevel.choices,
        default=TrustLevel.NEW,
        verbose_name="Niveau de confiance",
    )

    # Client créé à la volée lors d'une vente express (données minimales)
    is_express = models.BooleanField(
        default=False,
        verbose_name="Client express",
    )

    # Notes libres de l'opérateur
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes",
    )

    # Solde de dette courant — mis à jour par DebtService à chaque mouvement.
    # Positif = le client doit de l'argent à la boutique.
    debt_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name="Solde de dette",
    )

    # --- Meta & représentation ------------------------------------------

    class Meta:
        ordering = ["name"]
        verbose_name = "Client"
        verbose_name_plural = "Clients"

    def __str__(self) -> str:
        return f"{self.name} ({self.phone})"


class DebtMovement(TenantOwnedModel):
    """
    Écriture de dette client — append-only.
    Chaque vente à crédit, remboursement ou ajustement crée une ligne.
    Le solde du Customer est recalculé par DebtService après chaque écriture.
    """

    class Type(models.TextChoices):
        SALE = "sale", "Vente à crédit"
        REPAYMENT = "repayment", "Remboursement"
        ADJUSTMENT = "adjustment", "Ajustement"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="debt_movements",
        verbose_name="Client",
    )
    type = models.CharField(
        max_length=20,
        choices=Type.choices,
        verbose_name="Type",
    )
    # Montant positif = dette augmente ; négatif = dette diminue.
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Montant",
    )
    # Référence libre vers la vente ou le paiement d'origine.
    reference = models.CharField(max_length=255, blank=True, verbose_name="Référence")
    note = models.CharField(max_length=500, blank=True, verbose_name="Note")
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Enregistré par",
    )

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Mouvement de dette"
        verbose_name_plural = "Mouvements de dette"

    def __str__(self) -> str:
        return f"{self.get_type_display()} {self.amount} — {self.customer}"

    def save(self, *args, **kwargs):
        if self.pk and DebtMovement.objects.filter(pk=self.pk).exists():
            raise ValidationError(
                "DebtMovement est en lecture seule après création (append-only)."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # noqa: ARG002
        raise ValidationError(
            "La suppression d'un DebtMovement est interdite (piste d'audit)."
        )
