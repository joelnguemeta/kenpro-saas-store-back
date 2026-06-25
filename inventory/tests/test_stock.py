"""
Tests du stock ledger et de l'API mouvements : recalcul du cache StockLevel,
blocage de la survente, idempotence offline (client_uuid), append-only.
"""
import uuid

from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Tenant
from inventory.models import Location, Product, StockLevel, StockMovement
from inventory.services import InsufficientStock, StockLedger

MOVEMENTS_URL = "/api/v1/inventory/stock-movements/"


def make_tenant(slug):
    return Tenant.objects.create(slug=slug, name=slug, country="CM", currency="XAF")


class StockLedgerServiceTests(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("ledger-tenant")
        self.product = Product.objects.create(tenant=self.tenant, name="Riz", floor_price=1000)
        self.loc = Location.objects.create(tenant=self.tenant, name="Boutique")

    def _move(self, type_, qty, **kw):
        return StockLedger.record_movement(
            tenant=self.tenant, product=self.product, location=self.loc,
            type=type_, quantity=Decimal(qty), **kw,
        )

    def test_level_recalculated_from_movements(self):
        self._move(StockMovement.IN, "10")
        self._move(StockMovement.OUT, "3")
        level = StockLevel.objects.get(product=self.product, location=self.loc)
        self.assertEqual(level.quantity, Decimal("7.000"))

    def test_oversell_is_blocked(self):
        self._move(StockMovement.IN, "5")
        with self.assertRaises(InsufficientStock):
            self._move(StockMovement.OUT, "8")
        # Aucun mouvement de sortie n'a été persisté.
        self.assertEqual(StockMovement.objects.filter(type=StockMovement.OUT).count(), 0)

    def test_adjustment_allows_negative(self):
        self._move(StockMovement.ADJUSTMENT, "-2")
        level = StockLevel.objects.get(product=self.product, location=self.loc)
        self.assertEqual(level.quantity, Decimal("-2.000"))

    def test_client_uuid_is_idempotent(self):
        cid = uuid.uuid4()
        m1 = self._move(StockMovement.IN, "4", client_uuid=cid)
        m2 = self._move(StockMovement.IN, "4", client_uuid=cid)
        self.assertEqual(m1.id, m2.id)
        self.assertEqual(StockMovement.objects.count(), 1)


class StockMovementAPITests(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("api-stock-tenant")
        self.client.credentials(HTTP_X_TENANT_SLUG=self.tenant.slug)
        self.product = Product.objects.create(tenant=self.tenant, name="Lait", floor_price=600)
        self.loc = Location.objects.create(tenant=self.tenant, name="Stand")

    def _payload(self, type_, qty):
        return {"product": str(self.product.id), "location": str(self.loc.id),
                "type": type_, "quantity": qty}

    def test_create_movement_updates_level(self):
        resp = self.client.post(MOVEMENTS_URL, self._payload("in", "12"))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        level = StockLevel.objects.get(product=self.product, location=self.loc)
        self.assertEqual(level.quantity, Decimal("12.000"))

    def test_oversell_returns_400(self):
        self.client.post(MOVEMENTS_URL, self._payload("in", "5"))
        resp = self.client.post(MOVEMENTS_URL, self._payload("out", "9"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", resp.data)

    def test_movements_are_append_only(self):
        created = self.client.post(MOVEMENTS_URL, self._payload("in", "5")).data
        url = f"{MOVEMENTS_URL}{created['id']}/"
        self.assertEqual(self.client.patch(url, {"quantity": "99"}).status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(url).status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)
