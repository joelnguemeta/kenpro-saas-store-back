"""
App `repair` — Réparation d'appareils de KENPRO.

Modèles :
  - Device        : l'appareil physique confié par le client.
  - RepairTicket  : le ticket de réparation, avec cycle de vie complet.
  - StatusHistory : journal immuable des changements de statut (append-only).

Les permissions ABAC du ticket sont déclarées dans la Meta de RepairTicket ;
elles sont exposées via le système de permissions Django standard (content type).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from kenpro_store.db import TenantOwnedModel

User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Appareil
# ---------------------------------------------------------------------------

class Device(TenantOwnedModel):
    """
    Appareil physique appartenant à un client.
    Un même client peut déposer plusieurs appareils ; un même appareil peut
    revenir pour plusieurs réparations successives.
    """

    class Type(models.TextChoices):
        PHONE = "phone", "Téléphone"
        LAPTOP = "laptop", "Ordinateur portable"
        TABLET = "tablet", "Tablette"
        OTHER = "other", "Autre"

    customer = models.ForeignKey(
        "crm.Customer",
        on_delete=models.PROTECT,
        related_name="devices",
        verbose_name="Client",
    )
    type = models.CharField(
        max_length=20,
        choices=Type.choices,
        verbose_name="Type d'appareil",
    )
    brand = models.CharField(max_length=100, verbose_name="Marque")
    model = models.CharField(max_length=100, verbose_name="Modèle")

    # IMEI ou numéro de série — permet de retrouver l'historique de l'appareil
    imei_serial = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="IMEI / Numéro de série",
    )

    class Meta:
        ordering = ["brand", "model"]
        verbose_name = "Appareil"
        verbose_name_plural = "Appareils"

    def __str__(self) -> str:
        return f"{self.brand} {self.model} — {self.imei_serial}"


# ---------------------------------------------------------------------------
# Ticket de réparation
# ---------------------------------------------------------------------------

class RepairTicket(TenantOwnedModel):
    """
    Ticket de réparation : du dépôt de l'appareil jusqu'à sa restitution.

    Cycle de vie :
        received → diagnosed → quote_sent → approved → in_progress
                → tested → ready → delivered
        (ou)    → rejected / returned / cancelled (sorties anticipées)

    Chaque transition est tracée dans StatusHistory (append-only).
    """

    class Status(models.TextChoices):
        RECEIVED = "received", "Reçu"
        DIAGNOSED = "diagnosed", "Diagnostiqué"
        QUOTE_SENT = "quote_sent", "Devis envoyé"
        APPROVED = "approved", "Devis approuvé"
        IN_PROGRESS = "in_progress", "En cours de réparation"
        TESTED = "tested", "Testé"
        READY = "ready", "Prêt à restituer"
        DELIVERED = "delivered", "Restitué"
        REJECTED = "rejected", "Devis refusé"
        RETURNED = "returned", "Rendu sans réparation"
        CANCELLED = "cancelled", "Annulé"

    device = models.ForeignKey(
        Device,
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name="Appareil",
    )
    # Dupliqué ici pour accéder rapidement au client sans passer par Device
    customer = models.ForeignKey(
        "crm.Customer",
        on_delete=models.PROTECT,
        related_name="repair_tickets",
        verbose_name="Client",
    )
    declared_issue = models.TextField(verbose_name="Panne déclarée")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RECEIVED,
        verbose_name="Statut",
    )

    # Technicien assigné — null jusqu'à la décision ABAC (repair:assign)
    technician = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_repairs",
        verbose_name="Technicien",
    )

    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="repair_tickets",
        verbose_name="Atelier / Emplacement",
    )

    # Date de réception physique de l'appareil (peut différer de created_at)
    intake_at = models.DateTimeField(verbose_name="Reçu le")

    class Meta:
        ordering = ["-intake_at"]
        verbose_name = "Ticket de réparation"
        verbose_name_plural = "Tickets de réparation"

        # Permissions ABAC déclarées ici pour être gérables via le système
        # de permissions Django (groupes, rôles). Le préfixe "repair:" est
        # une convention interne — Django enregistre le codename tel quel.
        permissions = [
            ("repair:create",       "Créer un ticket de réparation"),
            ("repair:read_own",     "Voir ses propres tickets"),
            ("repair:read_all",     "Voir tous les tickets"),
            ("repair:assign",       "Assigner un technicien"),
            ("repair:diagnose",     "Enregistrer un diagnostic"),
            ("repair:update",       "Modifier un ticket"),
            ("repair:quote",        "Créer/envoyer un devis"),
            ("repair:close",        "Clôturer un ticket"),
            ("repair:part_consume", "Consommer une pièce sur un ticket"),
        ]

    def __str__(self) -> str:
        return f"Ticket #{self.pk} — {self.device} ({self.get_status_display()})"


# ---------------------------------------------------------------------------
# Historique des statuts (append-only)
# ---------------------------------------------------------------------------

class StatusHistory(TenantOwnedModel):
    """
    Journal immuable des transitions de statut d'un ticket.

    RÈGLE STRICTE : append-only.
      - save()   interdit toute modification d'une entrée déjà persistée.
      - delete() est bloqué inconditionnellement.
    Cela garantit une piste d'audit inaltérable sur tout le cycle de vie.
    """

    ticket = models.ForeignKey(
        RepairTicket,
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name="Ticket",
    )
    from_status = models.CharField(
        max_length=20,
        verbose_name="Statut précédent",
    )
    to_status = models.CharField(
        max_length=20,
        verbose_name="Nouveau statut",
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Modifié par",
    )
    # Note libre facultative (raison du refus, observations…)
    note = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Note",
    )

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Historique de statut"
        verbose_name_plural = "Historiques de statut"

    def __str__(self) -> str:
        return (
            f"Ticket #{self.ticket_id} : "
            f"{self.from_status} → {self.to_status} "
            f"par {self.changed_by}"
        )

    def save(self, *args, **kwargs):
        # Interdit toute modification après la première persistance
        if self.pk and StatusHistory.objects.filter(pk=self.pk).exists():
            raise ValidationError(
                "StatusHistory est en lecture seule après création (append-only)."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # noqa: ARG002
        raise ValidationError(
            "La suppression d'un StatusHistory est interdite (piste d'audit)."
        )
