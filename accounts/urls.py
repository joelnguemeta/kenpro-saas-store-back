from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CreateOrganizationView,
    OtpRequestView,
    OtpVerifyView,
    UserSearchView,
    TenantSettingsView,
    LoginView,
    MembershipViewSet,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PermissionViewSet,
    PinResetConfirmView,
    PinResetRequestView,
    PinScopeViewSet,
    PlanViewSet,
    RegisterOrganizationView,
    RegisterView,
    RoleViewSet,
    ServiceFlagViewSet,
    SubscriptionViewSet,
    TenantViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("tenants", TenantViewSet, basename="tenant")
router.register("roles", RoleViewSet, basename="role")
router.register("permissions", PermissionViewSet, basename="permission")
router.register("memberships", MembershipViewSet, basename="membership")
router.register("pin-scopes", PinScopeViewSet, basename="pinscope")
# Back-office Super Admin
router.register("admin/plans", PlanViewSet, basename="plan")
router.register("admin/subscriptions", SubscriptionViewSet, basename="subscription")
router.register("admin/service-flags", ServiceFlagViewSet, basename="serviceflag")

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("otp/request/", OtpRequestView.as_view(), name="otp-request"),
    path("otp/verify/", OtpVerifyView.as_view(), name="otp-verify"),
    path("register/", RegisterView.as_view(), name="register"),
    path("register/organization/", RegisterOrganizationView.as_view(), name="register-organization"),
    path("organizations/", CreateOrganizationView.as_view(), name="create-organization"),
    path("tenant-settings/", TenantSettingsView.as_view(), name="tenant-settings"),
    path("users/search/", UserSearchView.as_view(), name="user-search"),
    path("password-reset/request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("pin-reset/request/", PinResetRequestView.as_view(), name="pin-reset-request"),
    path("pin-reset/confirm/", PinResetConfirmView.as_view(), name="pin-reset-confirm"),
] + router.urls