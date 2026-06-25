"""
Tests de l'API catalogue : CRUD, génération auto du SKU, isolation tenant
et validation cross-tenant des FKs.
"""
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Tenant
from inventory.models import Category, Product

PRODUCTS_URL = "/api/v1/inventory/products/"
CATEGORIES_URL = "/api/v1/inventory/categories/"


def make_tenant(slug, name=None):
    return Tenant.objects.create(
        slug=slug, name=name or slug, country="CM", currency="XAF"
    )


class CatalogueAPITests(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("test-tenant")
        self.client.credentials(HTTP_X_TENANT_SLUG=self.tenant.slug)

    # --- CRUD + SKU auto -----------------------------------------------------

    def test_create_product_generates_sku(self):
        resp = self.client.post(PRODUCTS_URL, {"name": "Savon", "floor_price": "500.00"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["sku"], "KP-000001")
        # Le tenant n'est pas exposé en écriture mais bien rattaché.
        self.assertEqual(Product.objects.get(id=resp.data["id"]).tenant_id, self.tenant.id)

    def test_sku_is_sequential_per_tenant(self):
        self.client.post(PRODUCTS_URL, {"name": "A", "floor_price": "100"})
        resp = self.client.post(PRODUCTS_URL, {"name": "B", "floor_price": "200"})
        self.assertEqual(resp.data["sku"], "KP-000002")

    def test_sku_is_read_only(self):
        resp = self.client.post(
            PRODUCTS_URL, {"name": "X", "floor_price": "100", "sku": "HACK-1"}
        )
        self.assertEqual(resp.data["sku"], "KP-000001")

    def test_list_and_retrieve(self):
        created = self.client.post(PRODUCTS_URL, {"name": "Sucre", "floor_price": "800"}).data
        self.assertEqual(self.client.get(PRODUCTS_URL).data["count"], 1)
        detail = self.client.get(f"{PRODUCTS_URL}{created['id']}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["name"], "Sucre")

    # --- Isolation tenant ----------------------------------------------------

    def test_tenant_isolation_list_and_retrieve(self):
        mine = self.client.post(PRODUCTS_URL, {"name": "Mien", "floor_price": "100"}).data

        other = make_tenant("other-tenant")
        self.client.credentials(HTTP_X_TENANT_SLUG=other.slug)
        # Le tenant B ne voit pas le produit du tenant A.
        self.assertEqual(self.client.get(PRODUCTS_URL).data["count"], 0)
        # …et ne peut pas y accéder directement (404, pas 403).
        resp = self.client.get(f"{PRODUCTS_URL}{mine['id']}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_payload_tenant_is_ignored(self):
        other = make_tenant("other-tenant")
        resp = self.client.post(
            PRODUCTS_URL, {"name": "X", "floor_price": "100", "tenant": str(other.id)}
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Product.objects.get(id=resp.data["id"]).tenant_id, self.tenant.id)

    # --- Validation cross-tenant des FKs ------------------------------------

    def test_cannot_attach_foreign_tenant_category(self):
        other = make_tenant("other-tenant")
        foreign_cat = Category.objects.create(tenant=other, name="Autre")
        resp = self.client.post(
            PRODUCTS_URL,
            {"name": "X", "floor_price": "100", "category": str(foreign_cat.id)},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", resp.data)

    def test_can_attach_own_tenant_category(self):
        cat = Category.objects.create(tenant=self.tenant, name="Hygiène")
        resp = self.client.post(
            PRODUCTS_URL,
            {"name": "Savon", "floor_price": "500", "category": str(cat.id)},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["category"], cat.id)
