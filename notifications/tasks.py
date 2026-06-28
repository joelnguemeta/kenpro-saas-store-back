"""
Tâches Celery pour les alertes stock WhatsApp.

Déclenchement : une fois par jour par Celery Beat.
La tâche principale `dispatch_stock_alerts` itère sur tous les tenants
ayant une configuration active et délègue l'envoi à `send_stock_alert_for_tenant`.
"""
import urllib.parse

import requests
from celery import shared_task
from django.conf import settings
from django.db.models import F

from inventory.models import StockLevel


def _build_alert_message(tenant_name: str, alerts: list) -> str:
    critical = [a for a in alerts if a["level"] == "critical"]
    low = [a for a in alerts if a["level"] == "low"]

    lines = [
        f"🔔 *Alerte stock — {tenant_name}*",
        "",
    ]

    if critical:
        lines.append("🔴 *Rupture de stock*")
        for a in critical:
            lines.append(f"  • {a['sku']} {a['name']} @ {a['location']} → *{a['qty']} unité(s)*")
        lines.append("")

    if low:
        lines.append("🟡 *Stock bas (seuil d'alerte atteint)*")
        for a in low:
            lines.append(
                f"  • {a['sku']} {a['name']} @ {a['location']} "
                f"→ {a['qty']} / seuil {a['threshold']}"
            )
        lines.append("")

    lines.append("_Pensez à réapprovisionner pour éviter les ruptures._")
    return "\n".join(lines)


def _send_whatsapp(phone: str, message: str) -> bool:
    """
    Envoie un message WhatsApp.
    - Si WHATSAPP_API_URL est configuré → appel API WhatsApp Business (Meta).
    - Sinon → log uniquement (mode développement).
    Retourne True si envoyé, False sinon.
    """
    api_url = getattr(settings, "WHATSAPP_API_URL", "")
    token = getattr(settings, "WHATSAPP_API_TOKEN", "")
    phone_id = getattr(settings, "WHATSAPP_FROM_PHONE_ID", "")

    if api_url and token and phone_id:
        try:
            resp = requests.post(
                f"{api_url}/{phone_id}/messages",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "messaging_product": "whatsapp",
                    "to": phone,
                    "type": "text",
                    "text": {"body": message},
                },
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("WhatsApp send failed: %s", exc)
            raise
    else:
        # Mode dev — affiche le lien wa.me cliquable dans les logs
        import logging
        encoded = urllib.parse.quote(message)
        logging.getLogger(__name__).info(
            "WhatsApp alert (dev) → https://wa.me/%s?text=%s",
            phone.lstrip("+"),
            encoded[:80] + "...",
        )
        return True


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_stock_alert_for_tenant(self, tenant_id: str):
    """
    Construit et envoie l'alerte stock WhatsApp pour un tenant.
    Retryable 3 fois (espacées de 5 min) en cas d'échec réseau.
    """
    from notifications.models import StockAlertConfig

    try:
        config = StockAlertConfig.objects.select_related("tenant").get(
            tenant_id=tenant_id, is_enabled=True
        )
    except StockAlertConfig.DoesNotExist:
        return

    alerts_qs = (
        StockLevel.objects.select_related("product", "location")
        .filter(
            tenant_id=tenant_id,
            reorder_threshold__gt=0,
            quantity__lte=F("reorder_threshold"),
        )
        .order_by("quantity")
    )

    if alerts_qs.count() < config.min_alerts_to_send:
        return

    alerts = [
        {
            "level": "critical" if sl.quantity <= 0 else "low",
            "sku": sl.product.sku,
            "name": sl.product.name,
            "location": sl.location.name,
            "qty": float(sl.quantity),
            "threshold": float(sl.reorder_threshold),
        }
        for sl in alerts_qs
    ]

    message = _build_alert_message(config.tenant.name, alerts)
    try:
        _send_whatsapp(config.whatsapp_phone, message)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def dispatch_stock_alerts():
    """
    Point d'entrée Celery Beat — déclenché toutes les heures.
    Dispatche uniquement les tenants dont le send_time correspond à l'heure courante.
    """
    from datetime import datetime
    import pytz
    from notifications.models import StockAlertConfig

    tz = pytz.timezone("Africa/Douala")
    current_hour = datetime.now(tz).strftime("%H:00")

    configs = StockAlertConfig.objects.filter(
        is_enabled=True, send_time=current_hour
    ).values_list("tenant_id", flat=True)

    for tenant_id in configs:
        send_stock_alert_for_tenant.delay(str(tenant_id))
