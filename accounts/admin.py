from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Membership, PasswordResetToken, PinResetToken, PinScope, Plan, Role, RolePermission, ServiceFlag, Subscription, Tenant, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # BaseUserAdmin attend 'username' par défaut — on substitue par 'phone'
    ordering = ("phone",)
    list_display = ("phone", "full_name", "email", "is_active", "is_staff")
    search_fields = ("phone", "full_name", "email")
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Informations personnelles", {"fields": ("full_name", "email")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("phone", "password1", "password2"),
        }),
    )
    # BaseUserAdmin référence 'username_field' pour le filtre horizontal
    filter_horizontal = ("user_permissions",)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "country", "currency", "is_active", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "is_system", "is_editable")
    list_filter = ("is_system", "is_editable", "tenant")
    search_fields = ("name",)


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission", "constraints")
    search_fields = ("role__name", "permission__codename")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "is_active", "has_pin", "created_at")
    list_filter = ("is_active", "tenant")
    search_fields = ("user__phone", "role__name")
    # Le champ pin est exclu de l'édition directe — doit passer par set_pin()
    exclude = ("pin",)

    @admin.display(boolean=True, description="PIN défini")
    def has_pin(self, obj):
        return obj.has_pin


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "used", "is_valid")
    list_filter = ("used",)
    readonly_fields = ("token_hash", "created_at", "expires_at")

    @admin.display(boolean=True, description="Valide")
    def is_valid(self, obj):
        return obj.is_valid


@admin.register(PinResetToken)
class PinResetTokenAdmin(admin.ModelAdmin):
    list_display = ("membership", "created_at", "expires_at", "used", "is_valid")
    list_filter = ("used",)
    readonly_fields = ("token_hash", "created_at", "expires_at")

    @admin.display(boolean=True, description="Valide")
    def is_valid(self, obj):
        return obj.is_valid


@admin.register(PinScope)
class PinScopeAdmin(admin.ModelAdmin):
    list_display = ("tenant", "content_type", "label", "created_at")
    list_filter = ("tenant",)
    search_fields = ("label", "content_type__model")


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "monthly_price", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("tenant", "plan", "status", "trial_ends_at", "current_period_end", "created_at")
    list_filter = ("status", "plan")
    search_fields = ("tenant__name", "tenant__slug")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ServiceFlag)
class ServiceFlagAdmin(admin.ModelAdmin):
    list_display = ("tenant", "service", "is_enabled", "updated_at")
    list_filter = ("service", "is_enabled")
    search_fields = ("tenant__name", "service")