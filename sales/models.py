"""
App `sales` — Ventes de KENPRO.

Modèles : Sale (ticket), SaleLine (ligne avec snapshot des prix), Payment (paiement mixte).

Invariants clés :
  - Une vente validée est immuable (save() lève une erreur si status='validated').
  - Le prix final d'une ligne ne peut jamais descendre sous le prix plancher.
  - Un ticket peut comporter plusieurs paiements (cash + mobile money, etc.).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from kenpro_store.db import TenantOwnedModel

User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Vente (ticket)
# ---------------------------------------------------------------------------

class Sale(TenantOwnedModel):
    """
    Représente un ticket de vente, quel que soit le canal.
    Cycle de vie : draft → validated (immuable) ou cancelled.
    """

    class Channel(models.TextChoices):
        POS = "pos", "Caisse (POS)"
        WHATSAPP = "whatsapp", "WhatsApp"
        ONLINE = "online", "Boutique en ligne"
        MARKETPLACE = "marketplace", "Marketplace"

    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        VALIDATED = "validated", "Validée"
        CANCELLED = "cancelled", "Annulée"

    # Numéro de ticket lisible (ex. TICK-000001), généré par le service
    reference = models.CharField(max_length=32, blank=True, verbose_name="Référence")

    channel = models.CharField(
        max_length=20,
        choices=Channel.choices,
        default=Channel.POS,
        verbose_name="Canal de vente",
    )

    # Client facultatif — une vente anonyme au comptoir reste possible
    customer = models.ForeignKey(
        "crm.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales",
        verbose_name="Client",
    )

    seller = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="sales_as_seller",
        verbose_name="Vendeur",
    )

    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="sales",
        verbose_name="Emplacement",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Statut",
    )

    # Totaux mis à jour par le service à chaque modification de ligne
    subtotal = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Sous-total"
    )
    total_discount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Remise totale"
    )
    total = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Total TTC"
    )

    # Horodatage de validation — null tant que la vente est en cours
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validée le")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Vente"
        verbose_name_plural = "Ventes"

    def __str__(self) -> str:
        ref = self.reference or str(self.id)
        return f"Vente {ref} — {self.get_status_display()}"

    def save(self, *args, **kwargs):
        # Une vente validée ne peut plus être modifiée (ticket émis = immuable)
        if self.pk:
            original = Sale.objects.filter(pk=self.pk).values("status").first()
            if original and original["status"] == self.Status.VALIDATED:
                raise ValidationError(
                    "Une vente validée est immuable. Créez un avoir si nécessaire."
                )

        # Horodatage automatique lors du passage en 'validated'
        if self.status == self.Status.VALIDATED and self.validated_at is None:
            self.validated_at = timezone.now()

        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Ligne de vente
# ---------------------------------------------------------------------------

class SaleLine(TenantOwnedModel):
    """
    Ligne d'un ticket : un produit, une quantité, et un snapshot complet des
    prix au moment de la vente. Le snapshot est essentiel pour l'audit : le
    prix catalogue peut changer après coup, l'historique reste intact.
    """

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Vente",
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="sale_lines",
        verbose_name="Produit",
    )

    quantity = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name="Quantité"
    )
    unit = models.CharField(max_length=32, default="unité", verbose_name="Unité")

    # --- Snapshot des prix (figé au moment de la vente) ------------------

    # Plancher : prix en dessous duquel le vendeur ne peut pas descendre
    floor_price = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Prix plancher (snapshot)"
    )
    # Prix de référence affiché dans le catalogue
    catalog_price = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Prix catalogue (snapshot)"
    )
    # Prix effectivement appliqué (peut être inférieur au catalogue, jamais au plancher)
    final_price = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Prix final"
    )

    # Remise éventuelle sur cette ligne (montant absolu)
    line_adjustment = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Ajustement ligne"
    )
    # Utilisateur ayant appliqué la remise (traçabilité)
    adjusted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Ajusté par",
    )

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Ligne de vente"
        verbose_name_plural = "Lignes de vente"

    def __str__(self) -> str:
        return f"{self.product.name} × {self.quantity} — {self.final_price}"

    def save(self, *args, **kwargs):
        # Règle métier : le prix final ne peut jamais être inférieur au plancher
        if self.final_price < self.floor_price:
            raise ValidationError(
                f"Le prix final ({self.final_price}) est inférieur au prix plancher "
                f"({self.floor_price}) pour le produit « {self.product_id} »."
            )
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Paiement
# ---------------------------------------------------------------------------

class Payment(TenantOwnedModel):
    """
    Tranche de paiement liée à une vente.
    Un ticket peut être réglé en plusieurs fois et via plusieurs moyens
    (ex. 5 000 cash + solde par Mobile Money).
    """

    class Method(models.TextChoices):
        CASH = "cash", "Espèces"
        MOMO = "momo", "Mobile Money (MTN)"
        ORANGE_MONEY = "orange_money", "Orange Money"
        CARD = "card", "Carte bancaire"
        CREDIT = "credit", "Crédit client"
        DEPOSIT = "deposit", "Acompte"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        CONFIRMED = "confirmed", "Confirmé"

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Vente",
    )
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
        verbose_name="Moyen de paiement",
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Montant"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIRMED,
        verbose_name="Statut",
    )
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Enregistré par",
    )

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"

    def __str__(self) -> str:
        return (
            f"{self.get_method_display()} {self.amount} "
            f"({self.get_status_display()}) — vente {self.sale_id}"
        )
