"""
Tests d'intégration — CRM / Customers.
Couvre : list, create, retrieve, update (put + patch), destroy,
         filtres, recherche, isolation tenant.
"""
from rest_framework import status

from crm.models import Customer
from tests.factories import TenantAPITestCase, make_customer, make_tenant

URL = "/api/v1/crm/customers/"


def detail(pk):
    return f"{URL}{pk}/"


class CustomerListTest(TenantAPITestCase):

    def test_liste_vide_par_defaut(self):
        r = self.client.get(URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)

    def test_liste_retourne_clients_du_tenant(self):
        make_customer(self.tenant, name="Alice")
        make_customer(self.tenant, name="Bob", phone="+237690000002")
        r = self.client.get(URL)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 2)

    def test_isolation_tenant(self):
        other = make_tenant("other")
        make_customer(other, name="Étranger", phone="+237690000099")
        r = self.client.get(URL)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)

    def test_filtre_par_type(self):
        make_customer(self.tenant, name="Particulier", phone="+237690000001", type="individual")
        make_customer(self.tenant, name="Entreprise", phone="+237690000002", type="business")
        r = self.client.get(URL, {"type": "business"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)
        self.assertEqual(r.data["data"]["results"][0]["name"], "Entreprise")

    def test_filtre_par_trust_level(self):
        make_customer(self.tenant, name="Nouveau", phone="+237690000001", trust_level="new")
        make_customer(self.tenant, name="Fiable", phone="+237690000002", trust_level="reliable")
        r = self.client.get(URL, {"trust_level": "reliable"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)

    def test_filtre_is_express(self):
        make_customer(self.tenant, name="Express", phone="+237690000001", is_express=True)
        make_customer(self.tenant, name="Normal", phone="+237690000002", is_express=False)
        r = self.client.get(URL, {"is_express": "true"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)

    def test_recherche_par_nom(self):
        make_customer(self.tenant, name="Alice Martin", phone="+237690000001")
        make_customer(self.tenant, name="Bob Nguemo", phone="+237690000002")
        r = self.client.get(URL, {"search": "Alice"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)

    def test_recherche_par_telephone(self):
        make_customer(self.tenant, name="Alice", phone="+237690000001")
        r = self.client.get(URL, {"search": "+237690000001"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)


class CustomerCreateTest(TenantAPITestCase):

    def test_creation_minimale(self):
        r = self.client.post(URL, {"name": "Alice", "phone": "+237690000001"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r.data["success"])
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Customer.objects.first().tenant, self.tenant)

    def test_creation_complete(self):
        payload = {
            "name": "SARL Mokolo",
            "phone": "+237690000002",
            "email": "mokolo@example.com",
            "type": "business",
            "niu": "M123456789",
            "trust_level": "reliable",
            "notes": "Client depuis 2020.",
        }
        r = self.client.post(URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        c = Customer.objects.get(id=r.data["data"]["id"])
        self.assertEqual(c.type, "business")
        self.assertEqual(c.niu, "M123456789")

    def test_client_express_sans_email(self):
        r = self.client.post(
            URL, {"name": "Client Express", "phone": "+237690000003", "is_express": True}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r.data["data"]["is_express"])

    def test_creation_sans_nom_rejete(self):
        r = self.client.post(URL, {"phone": "+237690000004"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_creation_sans_telephone_rejete(self):
        r = self.client.post(URL, {"name": "Alice"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_tenant_injecte_ignore_payload(self):
        other = make_tenant("other")
        r = self.client.post(
            URL, {"name": "X", "phone": "+237690000005", "tenant": str(other.id)}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Customer.objects.get(id=r.data["data"]["id"]).tenant, self.tenant)


class CustomerRetrieveTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.customer = make_customer(self.tenant)

    def test_retrieve_existant(self):
        r = self.client.get(detail(self.customer.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["name"], self.customer.name)

    def test_retrieve_autre_tenant_404(self):
        other = make_tenant("other")
        foreign = make_customer(other, phone="+237690000099")
        r = self.client.get(detail(foreign.id))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_inexistant_404(self):
        r = self.client.get(detail("00000000-0000-0000-0000-000000000000"))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class CustomerUpdateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.customer = make_customer(self.tenant)

    def test_put_complet(self):
        payload = {"name": "Alice Modifiée", "phone": "+237690000099"}
        r = self.client.put(detail(self.customer.id), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Alice Modifiée")

    def test_patch_partiel(self):
        r = self.client.patch(detail(self.customer.id), {"trust_level": "reliable"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.trust_level, "reliable")

    def test_patch_autre_tenant_404(self):
        other = make_tenant("other")
        foreign = make_customer(other, phone="+237690000099")
        r = self.client.patch(detail(foreign.id), {"name": "Hack"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class CustomerDestroyTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.customer = make_customer(self.tenant)

    def test_suppression_ok(self):
        r = self.client.delete(detail(self.customer.id))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Customer.objects.filter(id=self.customer.id).exists())

    def test_suppression_autre_tenant_404(self):
        other = make_tenant("other")
        foreign = make_customer(other, phone="+237690000099")
        r = self.client.delete(detail(foreign.id))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Customer.objects.filter(id=foreign.id).exists())
