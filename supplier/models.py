"""
App `supplier` — Fournisseurs et crédit fournisseur de KENPRO.

Architecture :
  - Supplier        : entité globale (partagée entre toutes les boutiques).
  - SupplierLink    : pont boutique × fournisseur ; porte le plafond de crédit.
  - CreditStatement : relevé de crédit courant pour un lien donné.
  - CreditEntry     : écriture comptable APPEND-ONLY (jamais modifiable, jamais supprimée).
  - CreditPayment   : tranche de remboursement déclarée puis confirmée.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from kenpro_store.db import TenantOwnedModel, TimeStampedModel, UUIDModel

User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Entité globale
# ---------------------------------------------------------------------------

class Supplier(UUIDModel, TimeStampedModel):
    """
    Fournisseur global — non rattaché à un tenant.
    Une même entreprise peut approvisionner plusieurs boutiques KENPRO.
    """

    name = models.CharField(max_length=255, verbose_name="Nom")
    phone = models.CharField(max_length=20, verbose_name="Téléphone")
    email = models.EmailField(blank=True, null=True, verbose_name="E-mail")

    class Meta:
        ordering = ["name"]
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Lien boutique × fournisseur
# ---------------------------------------------------------------------------

class SupplierLink(TenantOwnedModel):
    """
    Relie un fournisseur à une boutique (tenant) et définit le plafond de crédit
    que cette boutique est autorisée à contracter envers ce fournisseur.
    """

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="links",
        verbose_name="Fournisseur",
    )
    # Plafond de crédit accordé par cette boutique au fournisseur
    credit_ceiling = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name="Plafond de crédit",
    )

    class Meta:
        ordering = ["supplier__name"]
        # Un fournisseur ne peut être lié qu'une seule fois à la même boutique
        unique_together = [("tenant", "supplier")]
        verbose_name = "Lien fournisseur"
        verbose_name_plural = "Liens fournisseurs"

    def __str__(self) -> str:
        return f"{self.supplier.name} — {self.tenant}"


# ---------------------------------------------------------------------------
# Relevé de crédit
# ---------------------------------------------------------------------------

class CreditStatement(TenantOwnedModel):
    """
    Relevé de crédit actif pour un SupplierLink donné.
    Un seul relevé « open » à la fois par lien ; il passe en « settled » quand
    le solde est soldé.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Ouvert"
        SETTLED = "settled", "Soldé"

    supplier_link = models.ForeignKey(
        SupplierLink,
        on_delete=models.PROTECT,
        related_name="statements",
        verbose_name="Lien fournisseur",
    )
    # Solde courant — mis à jour par le service, non calculé à la volée
    balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name="Solde",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name="Statut",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Relevé de crédit"
        verbose_name_plural = "Relevés de crédit"

    def __str__(self) -> str:
        return f"Relevé {self.id} — {self.supplier_link.supplier.name} ({self.get_status_display()})"


# ---------------------------------------------------------------------------
# Écriture de crédit (APPEND-ONLY)
# ---------------------------------------------------------------------------

class CreditEntry(UUIDModel, TimeStampedModel):
    """
    Écriture comptable sur un relevé de crédit.

    RÈGLE STRICTE : append-only.
      - save() interdit la modification d'une instance déjà persistée.
      - delete() est bloqué inconditionnellement.
    Cela garantit une piste d'audit inaltérable.
    """

    class Type(models.TextChoices):
        CHARGE = "charge", "Débit (achat)"
        ADJUSTMENT = "adjustment", "Ajustement"
        CREDIT_NOTE = "credit_note", "Avoir"

    statement = models.ForeignKey(
        CreditStatement,
        on_delete=models.PROTECT,
        related_name="entries",
        verbose_name="Relevé",
    )
    type = models.CharField(
        max_length=20,
        choices=Type.choices,
        verbose_name="Type d'écriture",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Montant",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Créé par",
    )

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Écriture de crédit"
        verbose_name_plural = "Écritures de crédit"

    def __str__(self) -> str:
        return f"{self.get_type_display()} {self.amount} — relevé {self.statement_id}"

    def save(self, *args, **kwargs):
        # Interdit toute modification après la première persistance
        if self.pk and CreditEntry.objects.filter(pk=self.pk).exists():
            raise ValidationError(
                "CreditEntry est en lecture seule après création (append-only)."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # noqa: ARG002
        raise ValidationError(
            "La suppression d'une CreditEntry est interdite (piste d'audit)."
        )


# ---------------------------------------------------------------------------
# Tranche de remboursement
# ---------------------------------------------------------------------------

class CreditPayment(UUIDModel, TimeStampedModel):
    """
    Paiement partiel ou total d'un relevé de crédit.
    Déclaré par l'opérateur puis confirmé par le fournisseur.
    """

    class Method(models.TextChoices):
        CASH = "cash", "Espèces"
        MOMO = "momo", "Mobile Money (MTN)"
        ORANGE_MONEY = "orange_money", "Orange Money"

    class Status(models.TextChoices):
        DECLARED = "declared", "Déclaré"
        CONFIRMED = "confirmed", "Confirmé"

    statement = models.ForeignKey(
        CreditStatement,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name="Relevé",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Montant",
    )
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
        verbose_name="Moyen de paiement",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DECLARED,
        verbose_name="Statut",
    )
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Enregistré par",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Remboursement"
        verbose_name_plural = "Remboursements"

    def __str__(self) -> str:
        return (
            f"{self.amount} ({self.get_method_display()}) — "
            f"{self.get_status_display()} — relevé {self.statement_id}"
        )
