"""
Tests d'intégration — Sales / Payment.
Couvre : list, create, retrieve, destroy.
PUT/PATCH sont désactivés sur ce viewset.
"""
from rest_framework import status

from sales.models import Payment
from tests.factories import (
    TenantAPITestCase,
    make_sale,
    make_tenant,
)

URL = "/api/v1/sales/payments/"


def detail(pk):
    return f"{URL}{pk}/"


def make_payment_payload(sale, amount="5000.00", method="cash"):
    return {"sale": str(sale.id), "amount": amount, "method": method}


class PaymentListTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.sale = make_sale(self.tenant, self.user)

    def test_filtre_par_vente(self):
        self.client.post(URL, make_payment_payload(self.sale), format="json")
        r = self.client.get(URL, {"sale": str(self.sale.id)})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)

    def test_isolation_tenant(self):
        other = make_tenant("other")
        other_sale = make_sale(other, self.user)
        Payment.objects.create(
            tenant=other, sale=other_sale, amount="1000",
            method="cash", recorded_by=self.user,
        )
        r = self.client.get(URL)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)


class PaymentCreateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.sale = make_sale(self.tenant, self.user)

    def test_creation_cash(self):
        r = self.client.post(URL, make_payment_payload(self.sale), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        p = Payment.objects.get(id=r.data["data"]["id"])
        self.assertEqual(p.recorded_by, self.user)
        self.assertEqual(p.status, "confirmed")

    def test_creation_momo(self):
        payload = make_payment_payload(self.sale, method="momo")
        r = self.client.post(URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["data"]["method"], "momo")

    def test_creation_sans_montant_rejete(self):
        r = self.client.post(URL, {"sale": str(self.sale.id), "method": "cash"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_paiement_mixte_plusieurs_par_vente(self):
        self.client.post(URL, make_payment_payload(self.sale, "3000"), format="json")
        self.client.post(URL, make_payment_payload(self.sale, "2000", "momo"), format="json")
        self.assertEqual(Payment.objects.filter(sale=self.sale).count(), 2)


class PaymentRetrieveTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.payment = Payment.objects.create(
            tenant=self.tenant,
            sale=make_sale(self.tenant, self.user),
            amount="5000", method="cash", recorded_by=self.user,
        )

    def test_retrieve_ok(self):
        r = self.client.get(detail(self.payment.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_put_non_autorise(self):
        r = self.client.put(detail(self.payment.id), {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_patch_non_autorise(self):
        r = self.client.patch(detail(self.payment.id), {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class PaymentDestroyTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.sale = make_sale(self.tenant, self.user)

    def test_suppression_ok(self):
        payment = Payment.objects.create(
            tenant=self.tenant, sale=self.sale,
            amount="5000", method="cash", recorded_by=self.user,
        )
        r = self.client.delete(detail(payment.id))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Payment.objects.filter(id=payment.id).exists())
