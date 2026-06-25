"""
Tests d'intégration — Supplier / CreditStatement.
Couvre : list (allégée), create, retrieve (avec entries + payments),
         update, destroy, filtre par lien/statut.
"""
from rest_framework import status

from supplier.models import CreditStatement
from tests.factories import (
    TenantAPITestCase,
    make_credit_statement,
    make_supplier_link,
    make_tenant,
)

URL = "/api/v1/supplier/statements/"


def detail(pk):
    return f"{URL}{pk}/"


class CreditStatementListTest(TenantAPITestCase):

    def test_liste_vide(self):
        r = self.client.get(URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)

    def test_isolation_tenant(self):
        make_credit_statement(self.tenant)
        other = make_tenant("other")
        make_credit_statement(other)
        r = self.client.get(URL)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)

    def test_filtre_par_statut(self):
        make_credit_statement(self.tenant)
        r = self.client.get(URL, {"status": "open"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)
        r = self.client.get(URL, {"status": "settled"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)

    def test_liste_ne_contient_pas_entries(self):
        make_credit_statement(self.tenant)
        r = self.client.get(URL)
        # La liste utilise le serializer allégé : pas de champ `entries`
        self.assertNotIn("entries", r.data["data"]["results"][0])


class CreditStatementCreateTest(TenantAPITestCase):

    def test_creation_ok(self):
        link = make_supplier_link(self.tenant)
        r = self.client.post(
            URL,
            {"supplier_link": str(link.id)},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        stmt = CreditStatement.objects.get(id=r.data["data"]["id"])
        self.assertEqual(stmt.tenant, self.tenant)
        self.assertEqual(stmt.status, "open")
        self.assertEqual(stmt.balance, 0)

    def test_creation_sans_link_rejete(self):
        r = self.client.post(URL, {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)


class CreditStatementRetrieveTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.stmt = make_credit_statement(self.tenant)

    def test_retrieve_contient_entries_et_payments(self):
        r = self.client.get(detail(self.stmt.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("entries", r.data["data"])
        self.assertIn("payments", r.data["data"])

    def test_retrieve_autre_tenant_404(self):
        other = make_tenant("other")
        foreign = make_credit_statement(other)
        r = self.client.get(detail(foreign.id))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class CreditStatementUpdateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.stmt = make_credit_statement(self.tenant)

    def test_patch_statut_settled(self):
        r = self.client.patch(detail(self.stmt.id), {"status": "settled"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.stmt.refresh_from_db()
        self.assertEqual(self.stmt.status, "settled")


class CreditStatementDestroyTest(TenantAPITestCase):

    def test_suppression_ok(self):
        stmt = make_credit_statement(self.tenant)
        r = self.client.delete(detail(stmt.id))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CreditStatement.objects.filter(id=stmt.id).exists())
