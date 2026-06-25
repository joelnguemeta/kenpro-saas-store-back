"""
Tests d'intégration — Repair / Device.
Couvre : list, create, retrieve, update, destroy,
         recherche, filtre par type, isolation tenant.
"""
from rest_framework import status

from repair.models import Device
from tests.factories import (
    TenantAPITestCase,
    make_customer,
    make_device,
    make_tenant,
)

URL = "/api/v1/repair/devices/"


def detail(pk):
    return f"{URL}{pk}/"


def make_device_payload(customer, device_type="phone", imei="123456789012345"):
    return {
        "customer": str(customer.id),
        "type": device_type,
        "brand": "Samsung",
        "model": "Galaxy A54",
        "imei_serial": imei,
    }


class DeviceListTest(TenantAPITestCase):

    def test_liste_vide(self):
        r = self.client.get(URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)

    def test_isolation_tenant(self):
        make_device(self.tenant)
        other = make_tenant("other")
        make_device(other)
        r = self.client.get(URL)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)

    def test_filtre_par_type(self):
        make_device(self.tenant)  # phone par défaut
        customer2 = make_customer(self.tenant, phone="+237690000099")
        Device.objects.create(
            tenant=self.tenant, customer=customer2,
            type="laptop", brand="HP", model="ProBook", imei_serial="999999999",
        )
        r = self.client.get(URL, {"type": "laptop"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)

    def test_recherche_par_imei(self):
        make_device(self.tenant)
        r = self.client.get(URL, {"search": "123456789012345"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)

    def test_recherche_par_marque(self):
        make_device(self.tenant)
        r = self.client.get(URL, {"search": "Samsung"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)


class DeviceCreateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.customer = make_customer(self.tenant)

    def test_creation_ok(self):
        r = self.client.post(URL, make_device_payload(self.customer), format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        device = Device.objects.get(id=r.data["data"]["id"])
        self.assertEqual(device.tenant, self.tenant)

    def test_tous_les_types_acceptes(self):
        for i, device_type in enumerate(["phone", "laptop", "tablet", "other"]):
            payload = make_device_payload(self.customer, device_type, f"IMEI{i:015d}")
            r = self.client.post(URL, payload, format="json")
            self.assertEqual(r.status_code, status.HTTP_201_CREATED, device_type)

    def test_creation_sans_imei_rejete(self):
        payload = {
            "customer": str(self.customer.id),
            "type": "phone", "brand": "Samsung", "model": "A54",
        }
        r = self.client.post(URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_type_invalide_rejete(self):
        payload = make_device_payload(self.customer, "drone")
        r = self.client.post(URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)


class DeviceRetrieveTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.device = make_device(self.tenant)

    def test_retrieve_ok(self):
        r = self.client.get(detail(self.device.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["imei_serial"], self.device.imei_serial)

    def test_retrieve_autre_tenant_404(self):
        other = make_tenant("other")
        foreign = make_device(other)
        r = self.client.get(detail(foreign.id))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class DeviceUpdateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.device = make_device(self.tenant)

    def test_patch_modele(self):
        r = self.client.patch(detail(self.device.id), {"model": "Galaxy S24"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.device.refresh_from_db()
        self.assertEqual(self.device.model, "Galaxy S24")

    def test_patch_autre_tenant_404(self):
        other = make_tenant("other")
        foreign = make_device(other)
        r = self.client.patch(detail(foreign.id), {"model": "Hack"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class DeviceDestroyTest(TenantAPITestCase):

    def test_suppression_ok(self):
        device = make_device(self.tenant)
        r = self.client.delete(detail(device.id))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Device.objects.filter(id=device.id).exists())
