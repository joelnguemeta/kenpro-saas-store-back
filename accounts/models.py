import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Utilisateur de la plateforme. Identifié par son numéro de téléphone (E.164).
    Le mot de passe est optionnel — l'authentification principale se fait par OTP email.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(null=True, blank=True)
    full_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self):
        return self.phone


class Tenant(models.Model):
    """
    Boutique / espace marchand. Unité d'isolation principale du multi-tenant.
    Chaque tenant a son pays et sa devise (pour la fiscalité et l'affichage).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    # Code ISO 3166-1 alpha-2, ex : "CM", "SN", "CI"
    country = models.CharField(max_length=2)
    # Code ISO 4217, ex : "XAF", "XOF", "GNF"
    currency = models.CharField(max_length=3)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"

    def __str__(self):
        return self.name


class Role(models.Model):
    """
    Rôle attribuable à un utilisateur dans un tenant.
    tenant=NULL → rôle système global (ex : SuperAdmin plateforme).
    tenant renseigné → rôle custom créé par ce tenant.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    tenant = models.ForeignKey(
        Tenant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="roles",
    )
    is_system = models.BooleanField(default=False)
    is_editable = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    # NULL = rôle permanent ; renseigné = rôle temporaire (ex : rôle promotionnel)
    expires_at = models.DateTimeField(null=True, blank=True)
    permissions = models.ManyToManyField(
        "auth.Permission",
        through="RolePermission",
        blank=True,
    )

    class Meta:
        verbose_name = "Rôle"
        verbose_name_plural = "Rôles"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_role_per_tenant"),
        ]

    def __str__(self):
        prefix = self.tenant.slug if self.tenant else "global"
        return f"{prefix} / {self.name}"


class RolePermission(models.Model):
    """
    Table de liaison entre Role et auth.Permission.
    Le champ constraints porte les plafonds ABAC (ex : {"max_discount_percent": 10}).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(
        "auth.Permission",
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    # Contraintes ABAC optionnelles portées par cette liaison
    constraints = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Permission de rôle"
        verbose_name_plural = "Permissions de rôle"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="unique_permission_per_role"),
        ]

    def __str__(self):
        return f"{self.role} → {self.permission.codename}"


class Membership(models.Model):
    """
    Appartenance d'un utilisateur à un tenant avec un rôle donné.
    tenant=NULL → rôle plateforme global (ex : staff Kenpro).
    expires_at=NULL → membership sans limite de durée.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    tenant = models.ForeignKey(
        Tenant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Expiration optionnelle — NULL = permanent
    expires_at = models.DateTimeField(null=True, blank=True)
    # PIN de sécurité — stocké haché (make_password/check_password de Django).
    # NULL = pas de PIN configuré sur ce membership.
    # Demandé à chaque action sur un PinScope du tenant.
    pin = models.CharField(max_length=128, null=True, blank=True)

    class Meta:
        verbose_name = "Appartenance"
        verbose_name_plural = "Appartenances"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tenant", "role"],
                name="unique_membership",
            ),
        ]

    def __str__(self):
        tenant_label = self.tenant.slug if self.tenant else "global"
        return f"{self.user} @ {tenant_label} [{self.role.name}]"

    @property
    def is_expired(self):
        """Retourne True si le membership a une date d'expiration dépassée."""
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @property
    def has_pin(self):
        return bool(self.pin)


class PinScope(models.Model):
    """
    Déclare qu'un type de modèle Django (ContentType) requiert la vérification
    du PIN de l'admin avant toute action dans ce tenant.
    L'admin choisit librement quels types il veut protéger.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="pin_scopes",
    )
    # Le type de modèle protégé, ex : "catalogue | produit"
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="pin_scopes",
    )
    # Description libre pour l'UI : "Suppression de remise", "Export clients"…
    label = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Périmètre PIN"
        verbose_name_plural = "Périmètres PIN"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "content_type"],
                name="unique_pin_scope_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.tenant.slug} → {self.content_type}"


class PasswordResetToken(models.Model):
    """
    Jeton à usage unique envoyé par email pour réinitialiser le mot de passe d'un User.
    Expire après PASSWORD_RESET_TOKEN_TTL_MINUTES (défaut 15 min).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Jeton réinitialisation mot de passe"
        verbose_name_plural = "Jetons réinitialisation mot de passe"

    def __str__(self):
        return f"PasswordResetToken({self.user} — {'utilisé' if self.used else 'valide'})"

    @property
    def is_valid(self) -> bool:
        return not self.used and timezone.now() <= self.expires_at


class PinResetToken(models.Model):
    """
    Jeton à usage unique envoyé par email pour réinitialiser le PIN d'un membership.
    Expire après PIN_RESET_TOKEN_TTL_MINUTES (défaut 15 min).
    Invalidé dès utilisation (used=True).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    membership = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name="pin_reset_tokens",
    )
    # Jeton aléatoire transmis dans le lien email (non haché — durée de vie courte)
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Jeton réinitialisation PIN"
        verbose_name_plural = "Jetons réinitialisation PIN"

    def __str__(self):
        return f"PinResetToken({self.membership} — {'utilisé' if self.used else 'valide'})"

    @property
    def is_valid(self) -> bool:
        return not self.used and timezone.now() <= self.expires_at
