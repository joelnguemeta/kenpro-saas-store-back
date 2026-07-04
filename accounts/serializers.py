from django.contrib.auth.models import Permission
from rest_framework import serializers

from .models import Membership, PinScope, Plan, Role, RolePermission, ServiceFlag, Subscription, Tenant, TenantSettings, User
from .phone import normalize_phone


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "phone", "email", "full_name", "is_active", "must_change_password", "date_joined"]
        read_only_fields = ["id", "must_change_password", "date_joined"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["id", "phone", "email", "full_name", "password"]
        read_only_fields = ["id"]

    def validate_phone(self, value):
        try:
            return normalize_phone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def create(self, validated_data):
        from .services import UserService
        password = validated_data.pop("password", None)
        return UserService.create(password=password, **validated_data)


class RegisterSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    # Optionnel — auth principale par OTP
    password = serializers.CharField(min_length=8, required=False, write_only=True)

    def validate_phone(self, value):
        try:
            value = normalize_phone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Un compte avec ce numéro existe déjà.")
        return value

    def create(self, validated_data):
        from .services import UserService
        password = validated_data.pop("password", None)
        return UserService.create(password=password, **validated_data)


class RegisterOrganizationSerializer(serializers.Serializer):
    """Inscription d'une organisation : compte + boutique (tenant) + rôle admin."""

    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    password = serializers.CharField(min_length=8, write_only=True)
    organization_name = serializers.CharField(max_length=255)
    country = serializers.CharField(max_length=2, default="CM")
    currency = serializers.CharField(max_length=3, default="XAF")

    def validate(self, attrs):
        # Le pays choisi pour l'organisation pilote l'interprétation du
        # numéro local : « 77 123 45 67 » + country=SN → +221771234567.
        try:
            attrs["phone"] = normalize_phone(
                attrs["phone"], region=attrs.get("country", "CM").upper()
            )
        except ValueError as exc:
            raise serializers.ValidationError({"phone": str(exc)})
        if User.objects.filter(phone=attrs["phone"]).exists():
            raise serializers.ValidationError(
                {"phone": "Un compte avec ce numéro existe déjà."}
            )
        return attrs

    def create(self, validated_data):
        from .services import OrganizationRegistrationService
        return OrganizationRegistrationService.register(**validated_data)


class CreateOrganizationSerializer(serializers.Serializer):
    """Création de boutique par un utilisateur déjà connecté (onboarding)."""

    organization_name = serializers.CharField(max_length=255)
    country = serializers.CharField(max_length=2, default="CM")
    currency = serializers.CharField(max_length=3, default="XAF")

    def create(self, validated_data):
        from .services import OrganizationRegistrationService
        return OrganizationRegistrationService.create_for_user(
            user=self.context["request"].user, **validated_data
        )


# ---------------------------------------------------------------------------

class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "country", "currency", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


# ---------------------------------------------------------------------------

class PermissionSerializer(serializers.ModelSerializer):
    app_label = serializers.CharField(source="content_type.app_label", read_only=True)

    class Meta:
        model = Permission
        fields = ["id", "codename", "name", "content_type", "app_label"]


class RolePermissionSerializer(serializers.ModelSerializer):
    permission = PermissionSerializer(read_only=True)
    permission_id = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all(), source="permission", write_only=True
    )

    class Meta:
        model = RolePermission
        fields = ["id", "permission", "permission_id", "constraints"]
        read_only_fields = ["id"]


class RoleSerializer(serializers.ModelSerializer):
    role_permissions = RolePermissionSerializer(many=True, read_only=True)
    is_expired = serializers.SerializerMethodField()
    # Liste plate "app_label.codename" — consommée par le frontend pour le gating UI
    permissions = serializers.SerializerMethodField()
    # Écriture : liste d'IDs de auth.Permission à synchroniser sur le rôle
    permission_ids = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all(), many=True, write_only=True, required=False
    )

    class Meta:
        model = Role
        fields = [
            "id", "name", "tenant", "is_system", "is_editable",
            "description", "expires_at", "role_permissions", "is_expired",
            "permissions", "permission_ids",
        ]
        read_only_fields = ["id"]

    def get_is_expired(self, obj) -> bool:
        from .services import RoleService
        return RoleService.is_expired(obj)

    def get_permissions(self, obj) -> list[str]:
        return [
            f"{rp.permission.content_type.app_label}.{rp.permission.codename}"
            for rp in obj.role_permissions.all()
        ]

    def _sync_permissions(self, role, permissions):
        RolePermission.objects.filter(role=role).exclude(permission__in=permissions).delete()
        existing = set(
            RolePermission.objects.filter(role=role).values_list("permission_id", flat=True)
        )
        RolePermission.objects.bulk_create([
            RolePermission(role=role, permission=p) for p in permissions if p.id not in existing
        ])

    def create(self, validated_data):
        permissions = validated_data.pop("permission_ids", None)
        role = super().create(validated_data)
        if permissions is not None:
            self._sync_permissions(role, permissions)
        return role

    def update(self, instance, validated_data):
        permissions = validated_data.pop("permission_ids", None)
        role = super().update(instance, validated_data)
        if permissions is not None:
            self._sync_permissions(role, permissions)
        return role


# ---------------------------------------------------------------------------

class InviteMemberSerializer(serializers.Serializer):
    """
    Ajout d'un membre à une boutique par son numéro de téléphone.
    `email` est requis si le compte n'existe pas encore : le mot de passe
    généré y est envoyé (à changer obligatoirement à la 1re connexion).
    """

    phone = serializers.CharField(max_length=20)
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    tenant = serializers.PrimaryKeyRelatedField(queryset=Tenant.objects.all())
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())

    def validate_phone(self, value):
        try:
            return normalize_phone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))


class MembershipSerializer(serializers.ModelSerializer):
    has_pin = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Membership
        fields = [
            "id", "user", "tenant", "role",
            "is_active", "created_at", "expires_at",
            "has_pin", "is_expired",
        ]
        read_only_fields = ["id", "created_at", "has_pin", "is_expired"]

    def to_representation(self, instance):
        """Imbrique user/tenant/role en lecture (l'écriture reste par PK)."""
        data = super().to_representation(instance)
        data["user"] = UserSerializer(instance.user).data
        data["tenant"] = TenantSerializer(instance.tenant).data if instance.tenant else None
        data["role"] = RoleSerializer(instance.role).data
        return data


class SetPinSerializer(serializers.Serializer):
    pin = serializers.CharField(min_length=4, max_length=16, write_only=True)


class VerifyPinSerializer(serializers.Serializer):
    pin = serializers.CharField(write_only=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=8, write_only=True)


class PinResetRequestSerializer(serializers.Serializer):
    membership_id = serializers.UUIDField()


class PinResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_pin = serializers.CharField(min_length=4, max_length=16, write_only=True)


# ---------------------------------------------------------------------------

class PinScopeSerializer(serializers.ModelSerializer):
    content_type_label = serializers.SerializerMethodField()

    class Meta:
        model = PinScope
        fields = ["id", "tenant", "content_type", "content_type_label", "label", "created_at"]
        read_only_fields = ["id", "created_at", "content_type_label"]

    def get_content_type_label(self, obj) -> str:
        return str(obj.content_type)


# ---------------------------------------------------------------------------
# Back-office Super Admin
# ---------------------------------------------------------------------------

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "name", "monthly_price", "description", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class SubscriptionSerializer(serializers.ModelSerializer):
    is_in_trial = serializers.BooleanField(read_only=True)
    trial_expired = serializers.BooleanField(read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id", "tenant", "plan", "plan_name", "status",
            "trial_ends_at", "current_period_start", "current_period_end",
            "is_in_trial", "trial_expired",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "plan_name", "is_in_trial", "trial_expired",
            "created_at", "updated_at",
        ]


class StartTrialSerializer(serializers.Serializer):
    tenant = serializers.UUIDField()
    plan = serializers.UUIDField()
    trial_days = serializers.IntegerField(min_value=0, required=False)


class ActivateSerializer(serializers.Serializer):
    plan = serializers.UUIDField(required=False)


class ExtendTrialSerializer(serializers.Serializer):
    extra_days = serializers.IntegerField(min_value=1)


class ServiceFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceFlag
        fields = ["id", "tenant", "service", "is_enabled", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ServiceFlagInputSerializer(serializers.Serializer):
    tenant = serializers.UUIDField()
    service = serializers.CharField(max_length=50)


class TenantSettingsSerializer(serializers.ModelSerializer):
    """Config générale du tenant — surchargée par boutique via Location."""

    class Meta:
        model = TenantSettings
        fields = [
            "id", "display_name", "contact_phone", "whatsapp_number",
            "contact_email", "address", "receipt_footer", "email_signature",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
