"""
Tests d'intégration — Supplier / CreditEntry (append-only).
Couvre : list, create, retrieve.
PUT/PATCH/DELETE sont interdits.
"""
from rest_framework import status

from supplier.models import CreditEntry
from tests.factories import (
    TenantAPITestCase,
    make_credit_statement,
)

URL = "/api/v1/supplier/entries/"


def detail(pk):
    return f"{URL}{pk}/"


def make_entry_payload(statement, entry_type="charge", amount="10000.00"):
    return {"statement": str(statement.id), "type": entry_type, "amount": amount}


class CreditEntryListTest(TenantAPITestCase):

    def test_filtre_par_statement(self):
        stmt = make_credit_statement(self.tenant)
        CreditEntry.objects.create(
            statement=stmt, type="charge", amount=5000, created_by=self.user
        )
        r = self.client.get(URL, {"statement": str(stmt.id)})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)


class CreditEntryCreateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.stmt = make_credit_statement(self.tenant)

    def test_creation_charge(self):
        r = self.client.post(URL, make_entry_payload(self.stmt), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        entry = CreditEntry.objects.get(id=r.data["data"]["id"])
        self.assertEqual(entry.created_by, self.user)
        self.assertEqual(entry.type, "charge")

    def test_creation_avoir(self):
        r = self.client.post(URL, make_entry_payload(self.stmt, "credit_note", "5000"), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_creation_ajustement(self):
        r = self.client.post(URL, make_entry_payload(self.stmt, "adjustment", "2000"), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_type_invalide_rejete(self):
        payload = make_entry_payload(self.stmt, "unknown_type")
        r = self.client.post(URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)


class CreditEntryRetrieveTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        stmt = make_credit_statement(self.tenant)
        self.entry = CreditEntry.objects.create(
            statement=stmt, type="charge", amount=10000, created_by=self.user
        )

    def test_retrieve_ok(self):
        r = self.client.get(detail(self.entry.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_put_interdit(self):
        r = self.client.put(detail(self.entry.id), {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_patch_interdit(self):
        r = self.client.patch(detail(self.entry.id), {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_interdit(self):
        r = self.client.delete(detail(self.entry.id))
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
