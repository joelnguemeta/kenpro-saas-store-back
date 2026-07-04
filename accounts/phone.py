"""
Normalisation des numéros de téléphone en E.164 (+237655112233).

Tous les points d'entrée (inscription, connexion, invitation, création
d'utilisateur) passent par `normalize_phone` : un même numéro tapé
« +237 6 55 11 22 33 », « 00237655112233 » ou « 655112233 » aboutit
toujours à la même forme canonique en base.
"""
import phonenumbers
from django.conf import settings

# Région par défaut pour interpréter les numéros locaux (sans indicatif).
# ISO 3166-1 alpha-2 : CM, SN, CI, GA, BJ…
DEFAULT_REGION = getattr(settings, "DEFAULT_PHONE_REGION", "CM")


def normalize_phone(raw: str, region: str | None = None) -> str:
    """
    Convertit une saisie libre en E.164.

    Args:
        raw:    saisie utilisateur (espaces, points, tirets, 00, local…)
        region: indicatif pays par défaut pour les numéros locaux
                (défaut : settings.DEFAULT_PHONE_REGION → "CM")

    Returns:
        Le numéro canonique, ex : "+237655112233".

    Raises:
        ValueError si le numéro est invalide ou impossible à interpréter.
    """
    cleaned = (raw or "").strip()
    if not cleaned:
        raise ValueError("Numéro de téléphone requis.")

    try:
        parsed = phonenumbers.parse(cleaned, region or DEFAULT_REGION)
    except phonenumbers.NumberParseException:
        raise ValueError("Numéro de téléphone invalide.")

    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Numéro de téléphone invalide pour ce pays.")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_phone_or_none(raw: str, region: str | None = None) -> str | None:
    """Variante silencieuse : None si invalide (pour les recherches)."""
    try:
        return normalize_phone(raw, region)
    except ValueError:
        return None
