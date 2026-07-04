"""
Couche service de l'app accounts.
Toute la logique métier passe ici — les vues ne font qu'appeler ces fonctions.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.contenttypes.models import ContentType
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Membership, PasswordResetToken, PinResetToken, PinScope, Plan, Role, RolePermission, ServiceFlag, Subscription, Tenant, User, _hash_token


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_branded_email(
    subject: str,
    body_txt: str,
    body_html: str,
    recipients: list[str],
    *,
    tenant=None,
    location=None,
) -> None:
    """
    Envoie un email multipart (texte + HTML) avec le logo Kenpro embarqué
    en pièce jointe inline (référencé par `cid:kenpro-logo` dans le HTML).

    Si `tenant` est fourni, la signature effective (config générale du
    tenant, surchargée par la boutique le cas échéant) est ajoutée en fin
    de message.
    """
    from email.mime.image import MIMEImage
    from pathlib import Path

    if tenant is not None:
        from kenpro_store.branding import effective_settings

        cfg = effective_settings(tenant, location=location)
        if cfg["email_signature"]:
            body_txt = f"{body_txt}\n\n--\n{cfg['email_signature']}"
            signature_html = cfg["email_signature"].replace("\n", "<br>")
            body_html = body_html.replace(
                "</body>",
                f'<p style="color:#888;font-size:12px;margin-top:24px">--<br>{signature_html}</p></body>',
            )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=body_txt,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@kenpro.cm"),
        to=recipients,
    )
    msg.attach_alternative(body_html, "text/html")

    logo_path = Path(settings.BASE_DIR) / "static" / "email" / "logo.png"
    if logo_path.exists():
        image = MIMEImage(logo_path.read_bytes())
        image.add_header("Content-ID", "<kenpro-logo>")
        image.add_header("Content-Disposition", "inline", filename="logo.png")
        msg.attach(image)

    msg.send()


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserService:

    @staticmethod
    def create(phone: str, password: str | None = None, **kwargs) -> User:
        """Crée un utilisateur. Le mot de passe est optionnel (auth OTP)."""
        return User.objects.create_user(phone=phone, password=password, **kwargs)

    @staticmethod
    def get_by_phone(phone: str) -> User:
        return User.objects.get(phone=phone)


class OrganizationRegistrationService:
    """Inscription d'une organisation : user + tenant + rôle admin + membership."""

    ADMIN_ROLE_NAME = "Admin boutique"

    @classmethod
    @transaction.atomic
    def register(
        cls,
        phone: str,
        password: str,
        organization_name: str,
        country: str = "CM",
        currency: str = "XAF",
        **user_kwargs,
    ) -> Membership:
        user = UserService.create(phone=phone, password=password, **user_kwargs)
        return cls.create_for_user(user, organization_name, country, currency)

    @classmethod
    @transaction.atomic
    def create_for_user(
        cls,
        user: User,
        organization_name: str,
        country: str = "CM",
        currency: str = "XAF",
    ) -> Membership:
        """Crée la boutique d'un utilisateur déjà inscrit (onboarding post-login)."""
        from django.utils.text import slugify

        base_slug = slugify(organization_name) or "boutique"
        slug = base_slug
        i = 2
        while Tenant.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{i}"
            i += 1

        tenant = Tenant.objects.create(
            name=organization_name,
            slug=slug,
            country=country.upper(),
            currency=currency.upper(),
        )
        # Rôle admin sans permission explicite = accès complet au tenant
        role = Role.objects.create(
            name=cls.ADMIN_ROLE_NAME,
            tenant=tenant,
            is_system=True,
            is_editable=False,
            description="Propriétaire de la boutique — accès complet.",
        )
        # Premier point de vente créé d'office — l'organisation peut ensuite
        # en ajouter d'autres (boutiques, entrepôts, stands) dans les paramètres.
        from inventory.models import Location

        Location.objects.create(
            tenant=tenant,
            name="Boutique principale",
            type=Location.SHOP,
            is_default=True,
        )
        return Membership.objects.create(user=user, tenant=tenant, role=role)


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------

class TenantService:

    @staticmethod
    def create(name: str, slug: str, country: str, currency: str, **kwargs) -> Tenant:
        return Tenant.objects.create(
            name=name, slug=slug, country=country, currency=currency, **kwargs
        )


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------

class RoleService:

    @staticmethod
    def create(
        name: str,
        tenant: Tenant | None = None,
        *,
        is_system: bool = False,
        is_editable: bool = True,
        description: str = "",
        expires_at=None,
    ) -> Role:
        return Role.objects.create(
            name=name,
            tenant=tenant,
            is_system=is_system,
            is_editable=is_editable,
            description=description,
            expires_at=expires_at,
        )

    @staticmethod
    def assign_permission(role: Role, permission, constraints: dict | None = None) -> RolePermission:
        """Attache une auth.Permission à un rôle, avec contraintes ABAC optionnelles."""
        rp, _ = RolePermission.objects.get_or_create(
            role=role,
            permission=permission,
            defaults={"constraints": constraints or {}},
        )
        return rp

    @staticmethod
    def remove_permission(role: Role, permission) -> None:
        RolePermission.objects.filter(role=role, permission=permission).delete()

    @staticmethod
    def is_expired(role: Role) -> bool:
        if role.expires_at is None:
            return False
        return timezone.now() > role.expires_at


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

class MembershipService:

    @staticmethod
    @transaction.atomic
    def create(user: User, role: Role, tenant: Tenant | None = None, **kwargs) -> Membership:
        """Crée une appartenance user ↔ tenant ↔ role."""
        return Membership.objects.create(user=user, tenant=tenant, role=role, **kwargs)

    @staticmethod
    @transaction.atomic
    def invite(
        phone: str,
        tenant: Tenant,
        role: Role,
        full_name: str = "",
        email: str = "",
    ) -> Membership:
        """
        Ajoute un membre à une boutique par son numéro de téléphone.

        Si le compte n'existe pas encore :
          - il est créé avec un mot de passe généré aléatoirement,
          - le mot de passe est envoyé par email (email obligatoire),
          - `must_change_password` force son remplacement à la 1re connexion.
        """
        user = User.objects.filter(phone=phone).first()

        if user is None:
            if not email:
                raise ValueError(
                    "Un email est requis pour créer le compte : "
                    "le mot de passe généré y sera envoyé."
                )
            from django.utils.crypto import get_random_string

            temp_password = get_random_string(
                12, "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
            )
            user = UserService.create(
                phone=phone, full_name=full_name, email=email, password=temp_password
            )
            user.must_change_password = True
            user.save(update_fields=["must_change_password"])

            MembershipService._send_invite_email(
                user=user, tenant=tenant, temp_password=temp_password
            )

        if Membership.objects.filter(user=user, tenant=tenant).exists():
            raise ValueError("Cette personne est déjà membre de la boutique.")
        return Membership.objects.create(user=user, tenant=tenant, role=role)

    @staticmethod
    def _send_invite_email(user: User, tenant: Tenant, temp_password: str) -> None:
        """Envoie les identifiants générés au nouvel invité."""
        subject = f"Bienvenue dans l'équipe {tenant.name} — vos accès Kenpro Store"
        body_txt = (
            f"Bonjour {user.full_name or ''},\n\n"
            f"Vous avez été ajouté(e) à l'équipe de « {tenant.name} » sur Kenpro Store.\n\n"
            f"Vos identifiants de connexion :\n"
            f"  Téléphone : {user.phone}\n"
            f"  Mot de passe temporaire : {temp_password}\n\n"
            f"⚠️ Ce mot de passe est à usage unique : vous devrez en choisir un "
            f"nouveau dès votre première connexion.\n\n"
            f"À très vite !"
        )
        body_html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:520px;margin:0 auto;padding:24px">
  <div style="text-align:center;margin-bottom:24px">
    <img src="cid:kenpro-logo" alt="Kenpro" width="64" height="64" style="border-radius:14px">
  </div>
  <h2 style="color:#8a5a0a">Bienvenue dans l'équipe {tenant.name} !</h2>
  <p>Bonjour {user.full_name or ''},</p>
  <p>Vous avez été ajouté(e) à l'équipe de <strong>{tenant.name}</strong> sur Kenpro Store.</p>
  <div style="background:#faf6ec;border:1px solid #e5d9b8;border-radius:12px;padding:16px;margin:16px 0">
    <p style="margin:4px 0">📱 <strong>Téléphone :</strong> {user.phone}</p>
    <p style="margin:4px 0">🔑 <strong>Mot de passe temporaire :</strong>
       <code style="background:#fff;padding:2px 8px;border-radius:6px;font-size:15px">{temp_password}</code></p>
  </div>
  <p style="color:#b45309">⚠️ Ce mot de passe est à usage unique : vous devrez en choisir
     un nouveau dès votre première connexion.</p>
  <p>À très vite !</p>
</body></html>"""
        send_branded_email(
            subject=subject,
            body_txt=body_txt,
            body_html=body_html,
            recipients=[user.email],
            tenant=tenant,
        )

    @staticmethod
    def set_pin(membership: Membership, raw_pin: str) -> None:
        """Hache et enregistre le PIN sur le membership."""
        if not raw_pin or len(raw_pin) < 4:
            raise ValueError("Le PIN doit comporter au moins 4 caractères.")
        membership.pin = make_password(raw_pin)
        membership.pin_failed_attempts = 0
        membership.pin_locked_until = None
        membership.save(update_fields=["pin", "pin_failed_attempts", "pin_locked_until"])

    @staticmethod
    def clear_pin(membership: Membership) -> None:
        """Supprime le PIN du membership."""
        membership.pin = None
        membership.save(update_fields=["pin"])

    PIN_MAX_ATTEMPTS = 5
    PIN_LOCKOUT_MINUTES = 15

    @staticmethod
    def verify_pin(membership: Membership, raw_pin: str) -> tuple[bool, bool]:
        """
        Retourne (correct, locked).
        Increments failed counter on wrong PIN; locks after PIN_MAX_ATTEMPTS failures.
        Resets counter on success.
        """
        now = timezone.now()
        if membership.pin_locked_until and now < membership.pin_locked_until:
            return False, True

        if not membership.pin:
            return False, False

        ok = check_password(raw_pin, membership.pin)
        if ok:
            membership.pin_failed_attempts = 0
            membership.pin_locked_until = None
            membership.save(update_fields=["pin_failed_attempts", "pin_locked_until"])
            return True, False

        membership.pin_failed_attempts += 1
        if membership.pin_failed_attempts >= MembershipService.PIN_MAX_ATTEMPTS:
            membership.pin_locked_until = now + timedelta(minutes=MembershipService.PIN_LOCKOUT_MINUTES)
        membership.save(update_fields=["pin_failed_attempts", "pin_locked_until"])
        return False, False

    @staticmethod
    def check_pin_required(membership: Membership, model_class) -> bool:
        """
        Retourne True si une action sur model_class dans ce tenant
        exige la vérification du PIN.
        """
        if not membership.tenant_id:
            return False
        ct = ContentType.objects.get_for_model(model_class)
        return PinScope.objects.filter(tenant_id=membership.tenant_id, content_type=ct).exists()

    @staticmethod
    def is_expired(membership: Membership) -> bool:
        return membership.is_expired


# ---------------------------------------------------------------------------
# Password reset (mot de passe oublié)
# ---------------------------------------------------------------------------

class PasswordResetService:

    TTL_MINUTES: int = getattr(settings, "PASSWORD_RESET_TOKEN_TTL_MINUTES", 15)

    @classmethod
    def request_reset(cls, email: str) -> tuple[PasswordResetToken, str]:
        """
        Cherche l'utilisateur par email, génère un jeton et envoie l'email.
        Retourne (token_obj, raw_value) — raw_value est transmis par email,
        jamais stocké en base.
        Lève ValueError si aucun compte n'est associé à cet email.
        """
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise ValueError("Aucun compte associé à cet email.")

        PasswordResetToken.objects.filter(user=user, used=False).update(used=True)

        token_value = secrets.token_urlsafe(32)
        token = PasswordResetToken.objects.create(
            user=user,
            token_hash=_hash_token(token_value),
            expires_at=timezone.now() + timedelta(minutes=cls.TTL_MINUTES),
        )
        cls._send_email(user, token_value)
        return token, token_value

    @staticmethod
    def confirm_reset(token_value: str, new_password: str) -> User:
        """
        Valide le jeton et applique le nouveau mot de passe.
        Lève ValueError si le jeton est invalide, expiré ou déjà utilisé.
        """
        try:
            token = PasswordResetToken.objects.select_related("user").get(token_hash=_hash_token(token_value))
        except PasswordResetToken.DoesNotExist:
            raise ValueError("Jeton invalide.")

        if not token.is_valid:
            raise ValueError("Jeton expiré ou déjà utilisé.")

        token.user.set_password(new_password)
        token.user.save(update_fields=["password"])
        token.used = True
        token.save(update_fields=["used"])
        return token.user

    @classmethod
    def _send_email(cls, user: User, token_value: str) -> None:
        context = {
            "full_name": user.full_name or "",
            "token": token_value,
            "ttl_minutes": cls.TTL_MINUTES,
        }
        subject = render_to_string("accounts/email/password_reset_subject.txt", context).strip()
        body_txt = render_to_string("accounts/email/password_reset.txt", context)
        body_html = render_to_string("accounts/email/password_reset.html", context)
        send_branded_email(subject, body_txt, body_html, [user.email])


# ---------------------------------------------------------------------------
# Password change (utilisateur connu)
# ---------------------------------------------------------------------------

class PasswordChangeService:

    @staticmethod
    def change(user: User, current_password: str, new_password: str) -> User:
        """
        Vérifie le mot de passe actuel puis applique le nouveau.
        Lève ValueError si le mot de passe actuel est incorrect
        ou si l'utilisateur n'en a pas (auth OTP uniquement).
        """
        if not user.has_usable_password():
            raise ValueError(
                "Ce compte utilise l'authentification OTP. "
                "Définissez d'abord un mot de passe via la réinitialisation."
            )
        if not user.check_password(current_password):
            raise ValueError("Mot de passe actuel incorrect.")
        user.set_password(new_password)
        # Le changement lève l'obligation posée à l'invitation
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        return user


# ---------------------------------------------------------------------------
# PinResetToken
# ---------------------------------------------------------------------------

class PinResetService:

    # Durée de validité du jeton (peut être surchargée via settings)
    TTL_MINUTES: int = getattr(settings, "PIN_RESET_TOKEN_TTL_MINUTES", 15)

    @classmethod
    def request_reset(cls, membership: Membership) -> tuple[PinResetToken, str]:
        """
        Génère un jeton de réinitialisation et envoie un email à l'utilisateur.
        Retourne (token_obj, raw_value) — raw_value est transmis par email,
        jamais stocké en base.
        Lève ValueError si l'utilisateur n'a pas d'adresse email.
        """
        email = membership.user.email
        if not email:
            raise ValueError("Cet utilisateur n'a pas d'adresse email enregistrée.")

        PinResetToken.objects.filter(membership=membership, used=False).update(used=True)

        token_value = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(minutes=cls.TTL_MINUTES)

        token = PinResetToken.objects.create(
            membership=membership,
            token_hash=_hash_token(token_value),
            expires_at=expires_at,
        )

        cls._send_email(email, token_value, membership)
        return token, token_value

    @staticmethod
    def confirm_reset(token_value: str, new_pin: str) -> Membership:
        """
        Valide le jeton et applique le nouveau PIN.
        Lève ValueError si le jeton est invalide, expiré ou déjà utilisé.
        """
        try:
            token = PinResetToken.objects.select_related("membership").get(token_hash=_hash_token(token_value))
        except PinResetToken.DoesNotExist:
            raise ValueError("Jeton invalide.")

        if not token.is_valid:
            raise ValueError("Jeton expiré ou déjà utilisé.")

        MembershipService.set_pin(token.membership, new_pin)
        token.used = True
        token.save(update_fields=["used"])
        return token.membership

    @staticmethod
    def _send_email(email: str, token_value: str, membership: Membership) -> None:
        tenant_label = membership.tenant.name if membership.tenant else "KENPRO"
        context = {
            "tenant_name": tenant_label,
            "token": token_value,
            "ttl_minutes": PinResetService.TTL_MINUTES,
        }
        subject = render_to_string("accounts/email/pin_reset_subject.txt", context).strip()
        body_txt = render_to_string("accounts/email/pin_reset.txt", context)
        body_html = render_to_string("accounts/email/pin_reset.html", context)
        send_branded_email(subject, body_txt, body_html, [email])


# ---------------------------------------------------------------------------
# PinScope
# ---------------------------------------------------------------------------

class PinScopeService:

    @staticmethod
    def protect(tenant: Tenant, model_class, label: str = "") -> PinScope:
        """Marque un type de modèle comme protégé par PIN dans ce tenant."""
        ct = ContentType.objects.get_for_model(model_class)
        scope, _ = PinScope.objects.get_or_create(
            tenant=tenant,
            content_type=ct,
            defaults={"label": label},
        )
        return scope

    @staticmethod
    def unprotect(tenant: Tenant, model_class) -> None:
        """Retire la protection PIN sur ce type de modèle."""
        ct = ContentType.objects.get_for_model(model_class)
        PinScope.objects.filter(tenant=tenant, content_type=ct).delete()

    @staticmethod
    def is_protected(tenant: Tenant, model_class) -> bool:
        ct = ContentType.objects.get_for_model(model_class)
        return PinScope.objects.filter(tenant=tenant, content_type=ct).exists()


# ---------------------------------------------------------------------------
# Subscription (back-office Super Admin)
# ---------------------------------------------------------------------------

class SubscriptionService:
    """
    Pilote le cycle de vie des abonnements depuis le back-office Super Admin.
    Toutes les mutations passent par ici.
    """

    DEFAULT_TRIAL_DAYS: int = getattr(settings, "DEFAULT_TRIAL_DAYS", 180)

    @classmethod
    @transaction.atomic
    def start_trial(
        cls,
        tenant: Tenant,
        plan: Plan,
        trial_days: int | None = None,
    ) -> Subscription:
        """Crée l'abonnement initial en période d'essai pour un tenant."""
        days = trial_days if trial_days is not None else cls.DEFAULT_TRIAL_DAYS
        trial_ends_at = timezone.now() + timedelta(days=days) if days > 0 else None
        sub, created = Subscription.objects.get_or_create(
            tenant=tenant,
            defaults={
                "plan": plan,
                "status": Subscription.Status.TRIAL,
                "trial_ends_at": trial_ends_at,
            },
        )
        if not created:
            raise ValueError(f"Le tenant « {tenant.name} » a déjà un abonnement.")
        return sub

    @staticmethod
    @transaction.atomic
    def activate(subscription: Subscription, plan: Plan | None = None) -> Subscription:
        """
        Passe l'abonnement en 'active' (conversion après essai ou réactivation).
        Change de plan si fourni.
        """
        if subscription.status == Subscription.Status.ACTIVE:
            raise ValueError("L'abonnement est déjà actif.")
        if plan:
            subscription.plan = plan
        subscription.status = Subscription.Status.ACTIVE
        subscription.current_period_start = timezone.now()
        subscription.current_period_end = timezone.now() + timedelta(days=30)
        subscription.save(update_fields=[
            "plan", "status", "current_period_start", "current_period_end", "updated_at",
        ])
        return subscription

    @staticmethod
    @transaction.atomic
    def suspend(subscription: Subscription) -> Subscription:
        """Suspend l'abonnement (impayé ou décision admin)."""
        if subscription.status == Subscription.Status.SUSPENDED:
            raise ValueError("L'abonnement est déjà suspendu.")
        subscription.status = Subscription.Status.SUSPENDED
        subscription.save(update_fields=["status", "updated_at"])
        return subscription

    @staticmethod
    @transaction.atomic
    def change_plan(subscription: Subscription, plan: Plan) -> Subscription:
        """Change le plan sans modifier le statut."""
        subscription.plan = plan
        subscription.save(update_fields=["plan", "updated_at"])
        return subscription

    @staticmethod
    @transaction.atomic
    def extend_trial(subscription: Subscription, extra_days: int) -> Subscription:
        """Prolonge la période d'essai d'un nombre de jours supplémentaires."""
        if subscription.status != Subscription.Status.TRIAL:
            raise ValueError("Seul un abonnement en essai peut être prolongé.")
        if extra_days <= 0:
            raise ValueError("Le nombre de jours doit être positif.")
        base = max(subscription.trial_ends_at or timezone.now(), timezone.now())
        subscription.trial_ends_at = base + timedelta(days=extra_days)
        subscription.save(update_fields=["trial_ends_at", "updated_at"])
        return subscription


# ---------------------------------------------------------------------------
# ServiceFlag (activation des services métier par tenant)
# ---------------------------------------------------------------------------

class ServiceFlagService:
    """
    Active ou désactive un service métier vertical pour un tenant.
    Appelé par le Super Admin depuis le back-office.
    """

    @staticmethod
    def enable(tenant: Tenant, service: str) -> ServiceFlag:
        flag, _ = ServiceFlag.objects.update_or_create(
            tenant=tenant,
            service=service,
            defaults={"is_enabled": True},
        )
        return flag

    @staticmethod
    def disable(tenant: Tenant, service: str) -> ServiceFlag:
        flag, _ = ServiceFlag.objects.update_or_create(
            tenant=tenant,
            service=service,
            defaults={"is_enabled": False},
        )
        return flag

    @staticmethod
    def is_enabled(tenant: Tenant, service: str) -> bool:
        try:
            return ServiceFlag.objects.get(tenant=tenant, service=service).is_enabled
        except ServiceFlag.DoesNotExist:
            return False

    @staticmethod
    def list_for_tenant(tenant: Tenant):
        return ServiceFlag.objects.filter(tenant=tenant).order_by("service")

# ---------------------------------------------------------------------------
# OTP — connexion par code à usage unique (canal pluggable, cf. otp_channels)
# ---------------------------------------------------------------------------

class OtpService:
    """
    Génération et vérification des codes de connexion.
    L'envoi est délégué au canal actif (email aujourd'hui, SMS/WhatsApp
    demain) — cf. accounts.otp_channels : extension par configuration.
    """

    TTL_MINUTES: int = getattr(settings, "OTP_TTL_MINUTES", 10)
    CODE_LENGTH: int = 6

    @classmethod
    @transaction.atomic
    def request_code(cls, phone: str, channel_name: str | None = None) -> dict:
        """
        Génère et envoie un code à l'utilisateur identifié par son téléphone.
        Retourne {channel, masked_destination}. Lève ValueError si le compte
        n'existe pas ou si le canal est inutilisable (ex. pas d'email).
        """
        import secrets

        from .models import OtpCode
        from .otp_channels import get_channel
        from .phone import normalize_phone_or_none

        normalized = normalize_phone_or_none(phone) or phone
        user = User.objects.filter(phone=normalized, is_active=True).first()
        if user is None:
            raise ValueError("Aucun compte actif pour ce numéro.")

        channel = get_channel(channel_name)
        if channel.destination_for(user) is None:
            raise ValueError(
                f"Ce compte n'a pas de destination pour le canal « {channel.name} » "
                f"(ex. adresse email manquante)."
            )

        # Invalide les codes précédents non utilisés
        OtpCode.objects.filter(user=user, used_at__isnull=True).delete()

        code = "".join(secrets.choice("0123456789") for _ in range(cls.CODE_LENGTH))
        OtpCode.objects.create(
            user=user,
            channel=channel.name,
            code_hash=OtpCode.hash_code(code),
            expires_at=timezone.now() + timezone.timedelta(minutes=cls.TTL_MINUTES),
        )
        channel.send(user, code)

        return {
            "channel": channel.name,
            "masked_destination": channel.masked_destination(user),
        }

    @classmethod
    @transaction.atomic
    def verify_code(cls, phone: str, code: str) -> User:
        """
        Vérifie le code et retourne l'utilisateur. Compte les tentatives
        (5 max) et marque le code comme consommé. Lève ValueError sinon.
        """
        from .models import OtpCode
        from .phone import normalize_phone_or_none

        normalized = normalize_phone_or_none(phone) or phone
        user = User.objects.filter(phone=normalized, is_active=True).first()
        if user is None:
            raise ValueError("Code invalide ou expiré.")

        otp = (
            OtpCode.objects.select_for_update()
            .filter(user=user, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if otp is None or not otp.is_valid:
            raise ValueError("Code invalide ou expiré. Demandez un nouveau code.")

        if otp.code_hash != OtpCode.hash_code(code.strip()):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            remaining = OtpCode.MAX_ATTEMPTS - otp.attempts
            if remaining <= 0:
                raise ValueError("Trop de tentatives. Demandez un nouveau code.")
            raise ValueError(f"Code incorrect ({remaining} essai(s) restant(s)).")

        otp.used_at = timezone.now()
        otp.save(update_fields=["used_at"])
        return user
