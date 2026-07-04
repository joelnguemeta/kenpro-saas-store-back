"""
Résolution de l'identité commerciale : config générale du tenant,
surchargée champ par champ par la boutique (Location).

Usage :
    from kenpro_store.branding import effective_settings
    cfg = effective_settings(tenant, location=sale.location)
    cfg["whatsapp_number"]  # numéro de la boutique, sinon celui du tenant
"""

_FIELDS = (
    "contact_phone",
    "whatsapp_number",
    "contact_email",
    "address",
    "receipt_footer",
    "email_signature",
)


def effective_settings(tenant, location=None) -> dict:
    """
    Fusionne TenantSettings (base) et les surcharges de la Location.
    Une valeur vide sur la boutique = héritage de la config générale.
    Retourne toujours un dict complet (chaînes vides si rien de configuré).
    """
    from accounts.models import TenantSettings

    base, _ = TenantSettings.objects.get_or_create(tenant=tenant)

    cfg = {
        "display_name": base.display_name or tenant.name,
        "currency": tenant.currency,
    }
    for field in _FIELDS:
        tenant_value = getattr(base, field, "") or ""
        location_value = getattr(location, field, "") or "" if location else ""
        cfg[field] = location_value or tenant_value

    # Le nom affiché d'une boutique spécifique reste le nom commercial du
    # tenant — le nom de la Location est opérationnel (ex. "Entrepôt nord"),
    # mais on l'expose pour les gabarits qui veulent le mentionner.
    cfg["location_name"] = location.name if location else ""

    return cfg
