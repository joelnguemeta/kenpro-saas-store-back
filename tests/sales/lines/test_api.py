"""
Tests d'intégration — Sales / SaleLine.
Couvre : list, create, retrieve, update, destroy,
         règle métier final_price >= floor_price.
"""
from rest_framework import status

from sales.models import SaleLine
from tests.factories import (
    TenantAPITestCase,
    make_location,
    make_product,
    make_sale,
    make_tenant,
)

URL = "/api/v1/sales/lines/"


def detail(pk):
    return f"{URL}{pk}/"


def make_line_payload(sale, product, final_price="600.00", floor_price="500.00"):
    return {
        "sale": str(sale.id),
        "product": str(product.id),
        "quantity": "1.000",
        "unit": "unité",
        "floor_price": floor_price,
        "catalog_price": "700.00",
        "final_price": final_price,
    }


class SaleLineListTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.sale = make_sale(self.tenant, self.user)
        self.product = make_product(self.tenant)

    def test_filtre_par_vente(self):
        payload = make_line_payload(self.sale, self.product)
        self.client.post(URL, payload, format="json")
        r = self.client.get(URL, {"sale": str(self.sale.id)})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)

    def test_isolation_tenant(self):
        other = make_tenant("other")
        other_sale = make_sale(other, self.user)
        other_product = make_product(other, floor_price="100.00")
        SaleLine.objects.create(
            tenant=other,
            sale=other_sale,
            product=other_product,
            quantity=1,
            unit="unité",
            floor_price="100.00",
            catalog_price="150.00",
            final_price="140.00",
        )
        r = self.client.get(URL)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)


class SaleLineCreateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.sale = make_sale(self.tenant, self.user)
        self.product = make_product(self.tenant)

    def test_creation_ok(self):
        payload = make_line_payload(self.sale, self.product)
        r = self.client.post(URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SaleLine.objects.count(), 1)

    def test_final_price_sous_floor_price_rejete(self):
        payload = make_line_payload(self.sale, self.product, final_price="400.00", floor_price="500.00")
        r = self.client.post(URL, payload, format="json")
        self.assertIn(r.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY])

    def test_final_price_egal_floor_price_accepte(self):
        payload = make_line_payload(self.sale, self.product, final_price="500.00", floor_price="500.00")
        r = self.client.post(URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_line_adjustment_injecte_adjusted_by(self):
        payload = make_line_payload(self.sale, self.product)
        payload["line_adjustment"] = "50.00"
        r = self.client.post(URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        line = SaleLine.objects.get(id=r.data["data"]["id"])
        self.assertEqual(line.adjusted_by, self.user)


class SaleLineRetrieveTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        sale = make_sale(self.tenant, self.user)
        product = make_product(self.tenant)
        self.line = SaleLine.objects.create(
            tenant=self.tenant, sale=sale, product=product,
            quantity=2, unit="unité",
            floor_price="500.00", catalog_price="700.00", final_price="650.00",
        )

    def test_retrieve_ok(self):
        r = self.client.get(detail(self.line.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["id"], str(self.line.id))


class SaleLineUpdateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.sale = make_sale(self.tenant, self.user)
        self.product = make_product(self.tenant)
        self.line = SaleLine.objects.create(
            tenant=self.tenant, sale=self.sale, product=self.product,
            quantity=1, unit="unité",
            floor_price="500.00", catalog_price="700.00", final_price="600.00",
        )

    def test_patch_quantite(self):
        r = self.client.patch(detail(self.line.id), {"quantity": "3.000"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.line.refresh_from_db()
        self.assertEqual(self.line.quantity, 3)


class SaleLineDestroyTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.line = SaleLine.objects.create(
            tenant=self.tenant,
            sale=make_sale(self.tenant, self.user),
            product=make_product(self.tenant),
            quantity=1, unit="unité",
            floor_price="500.00", catalog_price="700.00", final_price="600.00",
        )

    def test_suppression_ok(self):
        r = self.client.delete(detail(self.line.id))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SaleLine.objects.filter(id=self.line.id).exists())
