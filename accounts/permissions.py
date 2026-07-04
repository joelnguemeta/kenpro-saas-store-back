"""
Permissions DRF basées sur les rôles Kenpro (Membership → Role → auth.Permission).

Règles :
- Staff plateforme (is_staff / is_superuser) → accès complet.
- Un rôle SANS aucune permission explicite = accès complet
  (compatibilité avec les rôles legacy type "Admin boutique").
- Un rôle avec des permissions explicites est limité à celles-ci.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


def get_role_permissions(user):
    """
    Retourne l'ensemble des permissions "app_label.codename" issues des
    memberships actifs de l'utilisateur, ou None si accès complet
    (staff, ou au moins un rôle sans restriction).
    """
    if not user or not user.is_authenticated:
        return set()
    if user.is_staff or user.is_superuser:
        return None

    from django.utils import timezone

    from .models import Membership

    memberships = (
        Membership.objects.filter(user=user, is_active=True)
        .select_related("role")
        .prefetch_related("role__role_permissions__permission__content_type")
    )

    perms: set[str] = set()
    now = timezone.now()
    has_membership = False
    for m in memberships:
        if m.expires_at and m.expires_at < now:
            continue
        role = m.role
        if role.expires_at and role.expires_at < now:
            continue
        has_membership = True
        role_perms = [
            f"{rp.permission.content_type.app_label}.{rp.permission.codename}"
            for rp in role.role_permissions.all()
        ]
        if not role_perms:
            # Rôle sans restriction → accès complet
            return None
        perms.update(role_perms)

    if not has_membership:
        # Aucun membership actif → aucun droit métier
        return set()
    return perms


class RoleModelPermissions(BasePermission):
    """
    Variante de DjangoModelPermissions alimentée par les rôles Kenpro.
    No-op (autorise) si la vue n'expose pas de modèle (APIView sans queryset).
    """

    perms_map = {
        "GET": "view",
        "OPTIONS": None,
        "HEAD": None,
        "POST": "add",
        "PUT": "change",
        "PATCH": "change",
        "DELETE": "delete",
    }

    def _get_model(self, view):
        queryset = getattr(view, "queryset", None)
        if queryset is not None:
            return queryset.model
        get_queryset = getattr(view, "get_queryset", None)
        if get_queryset is not None:
            try:
                return get_queryset().model
            except Exception:
                return None
        return None

    def has_permission(self, request, view):
        # Compte invité avec mot de passe temporaire : accès aux données
        # bloqué tant que le mot de passe n'a pas été changé (les endpoints
        # auth/mot de passe ont leurs propres permission_classes, non affectés).
        if getattr(request.user, "must_change_password", False):
            self.message = (
                "Vous devez d'abord changer votre mot de passe temporaire."
            )
            return False

        model = self._get_model(view)
        if model is None:
            return True

        action = self.perms_map.get(request.method)
        if action is None:
            return True

        user_perms = get_role_permissions(request.user)
        if user_perms is None:  # accès complet
            return True

        meta = model._meta
        required = f"{meta.app_label}.{action}_{meta.model_name}"
        return required in user_perms


class IsStaffOrTenantManager(BasePermission):
    """
    Autorise le staff plateforme, ou un gestionnaire de tenant
    (rôle avec accès complet ou détenant "accounts.change_role").
    Le filtrage par tenant est fait dans les viewsets.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        perms = get_role_permissions(user)
        if perms is None:
            return True
        if request.method in SAFE_METHODS:
            return "accounts.view_role" in perms or "accounts.change_role" in perms
        return "accounts.change_role" in perms


def user_tenant_ids(user):
    """IDs des tenants où l'utilisateur a un membership actif."""
    from .models import Membership

    return list(
        Membership.objects.filter(user=user, is_active=True, tenant__isnull=False)
        .values_list("tenant_id", flat=True)
    )
