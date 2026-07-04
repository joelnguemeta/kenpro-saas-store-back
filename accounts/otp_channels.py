"""
Canaux d'envoi OTP — architecture ouverte/fermée (OCP).

Chaque canal implémente `OtpChannel`. Le canal actif et les canaux
disponibles sont déclarés dans les settings, par chemin d'import :

    OTP_CHANNELS = {
        "email": "accounts.otp_channels.EmailOtpChannel",
        # Ajouter un canal = nouvelle classe + une ligne ici. Rien d'autre.
        # "sms":      "integrations.sms.TwilioOtpChannel",
        # "whatsapp": "integrations.wa.WhatsAppOtpChannel",
    }
    OTP_DEFAULT_CHANNEL = "email"

Aucun code existant n'est modifié pour brancher un nouveau canal.
"""
from abc import ABC, abstractmethod

from django.conf import settings
from django.utils.module_loading import import_string


class OtpChannel(ABC):
    """Contrat d'un canal d'envoi de code à usage unique."""

    #: Identifiant du canal (informatif, ex. pour les logs)
    name: str = "abstract"

    @abstractmethod
    def destination_for(self, user) -> str | None:
        """
        Retourne l'adresse de destination pour cet utilisateur
        (email, numéro…) ou None si le canal est inutilisable pour lui.
        """

    @abstractmethod
    def send(self, user, code: str) -> None:
        """Envoie le code. Lève une exception en cas d'échec d'envoi."""

    def masked_destination(self, user) -> str:
        """Destination partiellement masquée, affichable côté client."""
        dest = self.destination_for(user) or ""
        if "@" in dest:
            local, _, domain = dest.partition("@")
            return f"{local[:2]}•••@{domain}"
        return f"•••{dest[-4:]}" if len(dest) >= 4 else "•••"


class EmailOtpChannel(OtpChannel):
    """Envoi du code par email (canal par défaut)."""

    name = "email"

    def destination_for(self, user) -> str | None:
        return user.email or None

    def send(self, user, code: str) -> None:
        from .services import send_branded_email

        subject = f"{code} — votre code de connexion Kenpro Store"
        body_txt = (
            f"Bonjour {user.full_name or ''},\n\n"
            f"Votre code de connexion : {code}\n\n"
            f"Il expire dans quelques minutes. Si vous n'êtes pas à "
            f"l'origine de cette demande, ignorez ce message."
        )
        body_html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:480px;margin:0 auto;padding:24px">
  <div style="text-align:center;margin-bottom:24px">
    <img src="cid:kenpro-logo" alt="Kenpro" width="64" height="64" style="border-radius:14px">
  </div>
  <h2 style="color:#8a5a0a;text-align:center">Code de connexion</h2>
  <p>Bonjour {user.full_name or ''},</p>
  <div style="text-align:center;margin:24px 0">
    <span style="display:inline-block;background:#faf6ec;border:1px solid #e5d9b8;border-radius:12px;
                 padding:14px 28px;font-size:32px;font-weight:bold;letter-spacing:8px">{code}</span>
  </div>
  <p style="color:#888;font-size:13px;text-align:center">
    Ce code expire dans quelques minutes.<br>
    Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.
  </p>
</body></html>"""
        send_branded_email(
            subject=subject,
            body_txt=body_txt,
            body_html=body_html,
            recipients=[self.destination_for(user)],
        )


# ---------------------------------------------------------------------------
# Registre — résolu depuis les settings (OCP : extension par configuration)
# ---------------------------------------------------------------------------

_DEFAULT_CHANNELS = {"email": "accounts.otp_channels.EmailOtpChannel"}


def available_channels() -> dict[str, str]:
    return getattr(settings, "OTP_CHANNELS", _DEFAULT_CHANNELS)


def get_channel(name: str | None = None) -> OtpChannel:
    """
    Instancie le canal demandé (ou le canal par défaut des settings).
    Lève ValueError si le canal n'est pas déclaré.
    """
    channels = available_channels()
    name = name or getattr(settings, "OTP_DEFAULT_CHANNEL", "email")
    path = channels.get(name)
    if path is None:
        raise ValueError(f"Canal OTP inconnu : {name!r}. Déclarés : {list(channels)}")
    return import_string(path)()
