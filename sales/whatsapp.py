"""
Génération des liens WhatsApp pour les reçus de vente (F-28).

Approche : on construit un message texte formaté puis on l'encode dans
un lien wa.me/?text=... Le vendeur tape dessus → WhatsApp s'ouvre
avec le message pré-rempli, prêt à être envoyé au client.

Aucune dépendance externe — fonctionne hors-ligne jusqu'au moment de
l'envoi (l'application WhatsApp est locale sur le téléphone).
"""
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from .models import Sale


def _format_receipt(sale: Sale) -> str:
    """Compose le texte du reçu en français, lisible sur mobile."""
    tenant_name = sale.tenant.name
    lines = []

    lines.append(f"🧾 *Reçu — {tenant_name}*")
    lines.append(f"N° {sale.reference or str(sale.id)[:8].upper()}")
    lines.append(
        f"Date : {timezone.localtime(sale.validated_at).strftime('%d/%m/%Y %H:%M')
        if sale.validated_at else '—'}"
    )
    lines.append("")

    # Lignes de vente
    for line in sale.lines.select_related("product").all():
        name = line.product.name
        qty = int(line.quantity) if line.quantity == int(line.quantity) else line.quantity
        price = int(line.final_price) if line.final_price == int(line.final_price) else line.final_price
        lines.append(f"• {name} × {qty}  →  {price:,} {sale.tenant.currency}".replace(",", " "))

    lines.append("")

    # Totaux
    total = int(sale.total) if sale.total == int(sale.total) else sale.total
    lines.append(f"*Total : {total:,} {sale.tenant.currency}*".replace(",", " "))

    # Moyens de paiement
    payments = list(sale.payments.all())
    if payments:
        lines.append("")
        for p in payments:
            amt = int(p.amount) if p.amount == int(p.amount) else p.amount
            lines.append(f"  ✓ {p.get_method_display()} : {amt:,} {sale.tenant.currency}".replace(",", " "))

    lines.append("")
    lines.append(f"Merci pour votre confiance ! 🙏")

    return "\n".join(lines)


def receipt_whatsapp_link(sale: Sale, phone: str | None = None) -> dict:
    """
    Construit le lien wa.me pour partager le reçu d'une vente.

    Args:
        sale:  La vente (doit être validée et avoir ses lignes/paiements chargés).
        phone: Numéro E.164 du destinataire (optionnel).
                Si fourni → lien direct vers le contact.
                Sinon    → lien générique (le vendeur choisit le contact).

    Returns:
        {
            "whatsapp_url": "https://wa.me/237600000001?text=...",
            "receipt_text": "🧾 Reçu — ...",
        }
    """
    text = _format_receipt(sale)
    encoded = quote(text)

    if phone:
        # Nettoie le + du format E.164 (wa.me attend des chiffres seuls)
        clean_phone = phone.lstrip("+").replace(" ", "")
        url = f"https://wa.me/{clean_phone}?text={encoded}"
    else:
        url = f"https://wa.me/?text={encoded}"

    return {"whatsapp_url": url, "receipt_text": text}


def catalog_share_link(tenant) -> dict:
    """
    Construit le lien partageable vers le catalogue en ligne du tenant (F-29).
    Le frontend sert la page catalogue à /boutique/{slug}.
    """
    frontend_url = getattr(settings, "FRONTEND_URL", "https://app.kenpro.cm").rstrip("/")
    url = f"{frontend_url}/boutique/{tenant.slug}"
    text = f"🛍️ Découvrez notre boutique *{tenant.name}* !\n{url}"
    encoded = quote(text)
    whatsapp_url = f"https://wa.me/?text={encoded}"

    return {
        "catalog_url": url,
        "whatsapp_url": whatsapp_url,
        "share_text": text,
    }
