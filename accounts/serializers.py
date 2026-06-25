from django.contrib.auth.models import Permission
from rest_framework import serializers

from .models import Membership, PinScope, Role, RolePermission, Tenant, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "phone", "email", "full_name", "is_active", "date_joined"]
        read_only_fields = ["id", "date_joined"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["id", "phone", "email", "full_name", "password"]
        read_only_fields = ["id"]

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
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Un compte avec ce numéro existe déjà.")
        return value

    def create(self, validated_data):
        from .services import UserService
        password = validated_data.pop("password", None)
        return UserService.create(password=password, **validated_data)


# ---------------------------------------------------------------------------

class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "country", "currency", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


# ---------------------------------------------------------------------------

class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "codename", "name", "content_type"]


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

    class Meta:
        model = Role
        fields = [
            "id", "name", "tenant", "is_system", "is_editable",
            "description", "expires_at", "role_permissions", "is_expired",
        ]
        read_only_fields = ["id"]

    def get_is_expired(self, obj) -> bool:
        from .services import RoleService
        return RoleService.is_expired(obj)


# ---------------------------------------------------------------------------

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
    phone = serializers.CharField()
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