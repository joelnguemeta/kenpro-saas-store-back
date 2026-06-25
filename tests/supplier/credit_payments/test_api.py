"""
Tests d'intégration — Supplier / CreditPayment.
Couvre : list, create, retrieve, destroy, action confirm.
Suppression interdite si statut 'confirmed'.
"""
from rest_framework import status

from supplier.models import CreditPayment
from tests.factories import (
    TenantAPITestCase,
    make_credit_statement,
)

URL = "/api/v1/supplier/credit-payments/"


def detail(pk):
    return f"{URL}{pk}/"


def confirm_url(pk):
    return f"{URL}{pk}/confirm/"


def make_payment_payload(statement, amount="10000.00", method="cash"):
    return {"statement": str(statement.id), "amount": amount, "method": method}


class CreditPaymentListTest(TenantAPITestCase):

    def test_filtre_par_statement(self):
        stmt = make_credit_statement(self.tenant)
        CreditPayment.objects.create(
            statement=stmt, amount=5000, method="cash",
            recorded_by=self.user, status="declared",
        )
        r = self.client.get(URL, {"statement": str(stmt.id)})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)


class CreditPaymentCreateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.stmt = make_credit_statement(self.tenant)

    def test_creation_cash(self):
        r = self.client.post(URL, make_payment_payload(self.stmt), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        p = CreditPayment.objects.get(id=r.data["data"]["id"])
        self.assertEqual(p.recorded_by, self.user)
        self.assertEqual(p.status, "declared")

    def test_creation_momo(self):
        r = self.client.post(URL, make_payment_payload(self.stmt, method="momo"), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_creation_sans_montant_rejete(self):
        r = self.client.post(
            URL, {"statement": str(self.stmt.id), "method": "cash"}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)


class CreditPaymentConfirmTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        stmt = make_credit_statement(self.tenant)
        self.payment = CreditPayment.objects.create(
            statement=stmt, amount=5000, method="cash",
            recorded_by=self.user, status="declared",
        )

    def test_confirmation_declared(self):
        r = self.client.post(confirm_url(self.payment.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "confirmed")

    def test_confirmation_deja_confirme_rejete(self):
        self.payment.status = "confirmed"
        self.payment.save()
        r = self.client.post(confirm_url(self.payment.id))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class CreditPaymentDestroyTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.stmt = make_credit_statement(self.tenant)

    def test_suppression_declared_ok(self):
        p = CreditPayment.objects.create(
            statement=self.stmt, amount=5000, method="cash",
            recorded_by=self.user, status="declared",
        )
        r = self.client.delete(detail(p.id))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)

    def test_suppression_confirmed_interdite(self):
        p = CreditPayment.objects.create(
            statement=self.stmt, amount=5000, method="cash",
            recorded_by=self.user, status="confirmed",
        )
        r = self.client.delete(detail(p.id))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(CreditPayment.objects.filter(id=p.id).exists())

    def test_put_interdit(self):
        p = CreditPayment.objects.create(
            statement=self.stmt, amount=5000, method="cash",
            recorded_by=self.user,
        )
        r = self.client.put(detail(p.id), {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
