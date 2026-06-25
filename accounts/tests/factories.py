"""
Fonctions utilitaires partagées entre les suites de tests.
Pas de dépendance externe (pas de factory_boy).
"""
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APITestCase

from accounts.models import Membership, PinScope, Role, Tenant, User


class TenantAPITestCase(APITestCase):
    """
    Classe de base pour les tests API.
    Crée un tenant de test et l'injecte via le header X-Tenant-Slug
    afin que le TenantMiddleware ne bloque pas les requêtes.
    """
    tenant_slug = "test-tenant"

    def setUp(self):
        self.tenant = Tenant.objects.get_or_create(
            slug=self.tenant_slug,
            defaults={"name": "Test Tenant", "country": "CM", "currency": "XAF"},
        )[0]
        self.client.credentials(**{"HTTP_X_TENANT_SLUG": self.tenant_slug})


def make_user(phone="+237600000001", password=None, **kwargs) -> User:
    return User.objects.create_user(phone=phone, password=password, **kwargs)


def make_tenant(name="Boutique Test", slug="boutique-test", country="CM", currency="XAF", **kwargs) -> Tenant:
    return Tenant.objects.create(name=name, slug=slug, country=country, currency=currency, **kwargs)


def make_role(name="Caissier", tenant=None, **kwargs) -> Role:
    return Role.objects.create(name=name, tenant=tenant, **kwargs)


def make_membership(user=None, tenant=None, role=None, **kwargs) -> Membership:
    user = user or make_user(phone="+237600000099")
    tenant = tenant or make_tenant(slug="default-tenant")
    role = role or make_role(name="Vendeur", tenant=tenant)
    return Membership.objects.create(user=user, tenant=tenant, role=role, **kwargs)


def get_any_permission() -> Permission:
    """Récupère n'importe quelle permission Django existante."""
    return Permission.objects.first()


def get_content_type_for(model_class) -> ContentType:
    return ContentType.objects.get_for_model(model_class)
