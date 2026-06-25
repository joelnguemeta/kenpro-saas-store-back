from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    MembershipViewSet,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PinResetConfirmView,
    PinResetRequestView,
    PinScopeViewSet,
    RegisterView,
    RoleViewSet,
    TenantViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("tenants", TenantViewSet, basename="tenant")
router.register("roles", RoleViewSet, basename="role")
router.register("memberships", MembershipViewSet, basename="membership")
router.register("pin-scopes", PinScopeViewSet, basename="pinscope")

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("password-reset/request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("pin-reset/request/", PinResetRequestView.as_view(), name="pin-reset-request"),
    path("pin-reset/confirm/", PinResetConfirmView.as_view(), name="pin-reset-confirm"),
] + router.urls