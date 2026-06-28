"""
Couche service de l'app accounts.
Toute la logique métier passe ici — les vues ne font qu'appeler ces fonctions.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Membership, PasswordResetToken, PinResetToken, PinScope, Plan, Role, RolePermission, ServiceFlag, Subscription, Tenant, User, _hash_token


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
        send_mail(
            subject=subject,
            message=body_txt,
            html_message=body_html,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@kenpro.cm"),
            recipient_list=[user.email],
        )


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
        user.save(update_fields=["password"])
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
        send_mail(
            subject=subject,
            message=body_txt,
            html_message=body_html,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@kenpro.cm"),
            recipient_list=[email],
        )


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