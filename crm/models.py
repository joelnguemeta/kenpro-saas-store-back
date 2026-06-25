"""
App `crm` — Gestion de la relation client de KENPRO.

Modèles : Customer.
"""
from django.db import models

from kenpro_store.db import TenantOwnedModel


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

    # --- Meta & représentation ------------------------------------------

    class Meta:
        ordering = ["name"]
        verbose_name = "Client"
        verbose_name_plural = "Clients"

    def __str__(self) -> str:
        # Affichage : "Nom (téléphone)" pour un repérage immédiat
        return f"{self.name} ({self.phone})"
