"""
Factories partagées par toutes les suites de tests d'intégration.
Pas de dépendance externe (pas de factory_boy).
"""
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Tenant, User
from crm.models import Customer
from inventory.models import Location, Product
from repair.models import Device, RepairTicket
from sales.models import Sale
from supplier.models import CreditStatement, Supplier, SupplierLink


# ---------------------------------------------------------------------------
# Classe de base
# ---------------------------------------------------------------------------

class TenantAPITestCase(APITestCase):
    """
    Classe de base pour tous les tests API KENPRO.
    Crée un tenant de test, un utilisateur et injecte le header X-Tenant-Slug.
    """
    tenant_slug = "test-tenant"

    def setUp(self):
        self.tenant = Tenant.objects.get_or_create(
            slug=self.tenant_slug,
            defaults={"name": "Test Tenant", "country": "CM", "currency": "XAF"},
        )[0]
        self.user = make_user(phone="+237600000001")
        self.client.credentials(HTTP_X_TENANT_SLUG=self.tenant_slug)
        self.client.force_authenticate(user=self.user)


# ---------------------------------------------------------------------------
# Helpers de création
# ---------------------------------------------------------------------------

def make_tenant(slug="other-tenant", name=None, **kwargs) -> Tenant:
    return Tenant.objects.create(
        slug=slug, name=name or slug, country="CM", currency="XAF", **kwargs
    )


def make_user(phone="+237600000002", **kwargs) -> User:
    return User.objects.create_user(phone=phone, **kwargs)


def make_customer(tenant, name="Jean Dupont", phone="+237690000001", **kwargs) -> Customer:
    return Customer.objects.create(tenant=tenant, name=name, phone=phone, **kwargs)


def make_location(tenant, name="Boutique Centrale", **kwargs) -> Location:
    return Location.objects.create(tenant=tenant, name=name, **kwargs)


def make_product(tenant, name="Savon", floor_price="500.00", **kwargs) -> Product:
    return Product.objects.create(tenant=tenant, name=name, floor_price=floor_price, **kwargs)


def make_supplier(name="Fournisseur Test", phone="+237690000099", **kwargs) -> Supplier:
    return Supplier.objects.create(name=name, phone=phone, **kwargs)


def make_supplier_link(tenant, supplier=None, credit_ceiling="100000.00", **kwargs) -> SupplierLink:
    supplier = supplier or make_supplier()
    return SupplierLink.objects.create(
        tenant=tenant, supplier=supplier, credit_ceiling=credit_ceiling, **kwargs
    )


def make_credit_statement(tenant, supplier_link=None, **kwargs) -> CreditStatement:
    supplier_link = supplier_link or make_supplier_link(tenant)
    return CreditStatement.objects.create(tenant=tenant, supplier_link=supplier_link, **kwargs)


def make_device(tenant, customer=None, **kwargs) -> Device:
    customer = customer or make_customer(tenant)
    return Device.objects.create(
        tenant=tenant,
        customer=customer,
        type="phone",
        brand="Samsung",
        model="Galaxy A54",
        imei_serial="123456789012345",
        **kwargs,
    )


def make_repair_ticket(tenant, user, device=None, customer=None, location=None, **kwargs) -> RepairTicket:
    customer = customer or make_customer(tenant)
    device = device or make_device(tenant, customer=customer)
    location = location or make_location(tenant)
    return RepairTicket.objects.create(
        tenant=tenant,
        device=device,
        customer=customer,
        location=location,
        declared_issue="Écran cassé",
        intake_at=timezone.now(),
        **kwargs,
    )


def make_sale(tenant, user, location=None, **kwargs) -> Sale:
    location = location or make_location(tenant)
    return Sale.objects.create(
        tenant=tenant,
        seller=user,
        location=location,
        **kwargs,
    )
