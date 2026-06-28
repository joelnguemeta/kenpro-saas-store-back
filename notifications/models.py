"""
App `notifications` — Configuration des alertes par tenant.

Chaque tenant peut activer/désactiver les alertes stock WhatsApp
et configurer le numéro qui les reçoit (gérant, responsable stock…).
"""
from django.db import models

from kenpro_store.db import TenantOwnedModel


class StockAlertConfig(TenantOwnedModel):
    """
    Configuration des alertes stock WhatsApp pour un tenant.
    Un seul enregistrement par tenant (unique sur tenant via OneToOne).
    """

    class SendTime(models.TextChoices):
        MORNING = "08:00", "08h00"
        NOON = "12:00", "12h00"
        EVENING = "18:00", "18h00"

    is_enabled = models.BooleanField(
        default=True,
        verbose_name="Alertes activées",
    )
    # Numéro WhatsApp du destinataire au format E.164 (ex. +237600000001)
    whatsapp_phone = models.CharField(
        max_length=20,
        verbose_name="Numéro WhatsApp destinataire",
        help_text="Format E.164 : +237600000001",
    )
    send_time = models.CharField(
        max_length=5,
        choices=SendTime.choices,
        default=SendTime.MORNING,
        verbose_name="Heure d'envoi",
    )
    # Seuil minimum d'alertes avant envoi (évite les spams pour 1 seul article)
    min_alerts_to_send = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Nombre minimum d'alertes pour déclencher l'envoi",
    )

    class Meta:
        verbose_name = "Configuration alerte stock"
        verbose_name_plural = "Configurations alertes stock"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="unique_alert_config_per_tenant"),
        ]

    def __str__(self):
        status = "activée" if self.is_enabled else "désactivée"
        return f"Alerte stock {self.tenant} — {status} → {self.whatsapp_phone}"
