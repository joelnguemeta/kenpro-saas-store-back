"""
Tests d'intégration — Supplier / SupplierLink.
Couvre : list, create, retrieve, update, destroy,
         unicité (tenant, supplier), isolation tenant.
"""
from rest_framework import status

from supplier.models import SupplierLink
from tests.factories import (
    TenantAPITestCase,
    make_supplier,
    make_supplier_link,
    make_tenant,
)

URL = "/api/v1/supplier/links/"


def detail(pk):
    return f"{URL}{pk}/"


class SupplierLinkListTest(TenantAPITestCase):

    def test_isolation_tenant(self):
        make_supplier_link(self.tenant)
        other = make_tenant("other")
        make_supplier_link(other, make_supplier(phone="+237699000099"))
        r = self.client.get(URL)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)


class SupplierLinkCreateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.supplier = make_supplier()

    def test_creation_ok(self):
        r = self.client.post(
            URL,
            {"supplier": str(self.supplier.id), "credit_ceiling": "50000.00"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        link = SupplierLink.objects.get(id=r.data["data"]["id"])
        self.assertEqual(link.tenant, self.tenant)

    def test_unicite_tenant_supplier(self):
        make_supplier_link(self.tenant, self.supplier)
        r = self.client.post(
            URL,
            {"supplier": str(self.supplier.id), "credit_ceiling": "10000.00"},
            format="json",
        )
        # IntegrityError → 409 Conflict (violation de unique_together en base)
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)

    def test_meme_fournisseur_deux_tenants(self):
        """Un même fournisseur peut être lié à deux boutiques différentes."""
        make_supplier_link(self.tenant, self.supplier)
        other = make_tenant("other")
        link2 = SupplierLink.objects.create(
            tenant=other, supplier=self.supplier, credit_ceiling=20000
        )
        self.assertIsNotNone(link2.pk)


class SupplierLinkUpdateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.link = make_supplier_link(self.tenant)

    def test_patch_credit_ceiling(self):
        r = self.client.patch(detail(self.link.id), {"credit_ceiling": "200000.00"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.link.refresh_from_db()
        self.assertEqual(self.link.credit_ceiling, 200000)

    def test_patch_autre_tenant_404(self):
        other = make_tenant("other")
        foreign = make_supplier_link(other, make_supplier(phone="+237699000098"))
        r = self.client.patch(detail(foreign.id), {"credit_ceiling": "1.00"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class SupplierLinkDestroyTest(TenantAPITestCase):

    def test_suppression_ok(self):
        link = make_supplier_link(self.tenant)
        r = self.client.delete(detail(link.id))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SupplierLink.objects.filter(id=link.id).exists())
