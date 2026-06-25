"""
Tests d'intégration — Supplier / Supplier (entité globale).
Supplier n'est pas tenant-scopé : visible par tous, modifiable par tous.
"""
from rest_framework import status

from supplier.models import Supplier
from tests.factories import TenantAPITestCase, make_supplier

URL = "/api/v1/supplier/suppliers/"


def detail(pk):
    return f"{URL}{pk}/"


class SupplierListTest(TenantAPITestCase):

    def test_liste_vide(self):
        r = self.client.get(URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)

    def test_liste_retourne_tous_les_fournisseurs(self):
        make_supplier(name="A", phone="+237690000001")
        make_supplier(name="B", phone="+237690000002")
        r = self.client.get(URL)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 2)

    def test_recherche_par_nom(self):
        make_supplier(name="Sodiko", phone="+237690000001")
        make_supplier(name="Congelcam", phone="+237690000002")
        r = self.client.get(URL, {"search": "Sodiko"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)


class SupplierCreateTest(TenantAPITestCase):

    def test_creation_minimale(self):
        r = self.client.post(URL, {"name": "Sodiko", "phone": "+237690000001"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Supplier.objects.count(), 1)

    def test_creation_complete(self):
        payload = {"name": "Congelcam", "phone": "+237690000002", "email": "congelcam@cm.com"}
        r = self.client.post(URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Supplier.objects.first().email, "congelcam@cm.com")

    def test_creation_sans_nom_rejete(self):
        r = self.client.post(URL, {"phone": "+237690000003"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)


class SupplierRetrieveTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.supplier = make_supplier()

    def test_retrieve_ok(self):
        r = self.client.get(detail(self.supplier.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["name"], self.supplier.name)

    def test_retrieve_inexistant_404(self):
        r = self.client.get(detail("00000000-0000-0000-0000-000000000000"))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class SupplierUpdateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.supplier = make_supplier()

    def test_patch_telephone(self):
        r = self.client.patch(detail(self.supplier.id), {"phone": "+237699999999"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.phone, "+237699999999")

    def test_put_complet(self):
        payload = {"name": "Sodiko Révisé", "phone": "+237699999998"}
        r = self.client.put(detail(self.supplier.id), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.name, "Sodiko Révisé")


class SupplierDestroyTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.supplier = make_supplier()

    def test_suppression_ok(self):
        r = self.client.delete(detail(self.supplier.id))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Supplier.objects.filter(id=self.supplier.id).exists())
