"""
Tests d'intégration — Sales / Sale (ticket de vente).
Couvre : list, create, retrieve, update, destroy,
         actions validate et cancel, isolation tenant.
"""
from rest_framework import status

from sales.models import Sale
from tests.factories import (
    TenantAPITestCase,
    make_customer,
    make_location,
    make_sale,
    make_tenant,
)

URL = "/api/v1/sales/sales/"


def detail(pk):
    return f"{URL}{pk}/"


def action_url(pk, action):
    return f"{URL}{pk}/{action}/"


class SaleListTest(TenantAPITestCase):

    def test_liste_vide(self):
        r = self.client.get(URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)

    def test_liste_propre_au_tenant(self):
        make_sale(self.tenant, self.user)
        other = make_tenant("other")
        make_sale(other, self.user)
        r = self.client.get(URL)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)

    def test_filtre_par_status(self):
        make_sale(self.tenant, self.user)
        r = self.client.get(URL, {"status": "draft"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)
        r = self.client.get(URL, {"status": "validated"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)


class SaleCreateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.location = make_location(self.tenant)

    def test_creation_minimale(self):
        r = self.client.post(URL, {"location": str(self.location.id)}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Sale.objects.count(), 1)
        sale = Sale.objects.first()
        self.assertEqual(sale.tenant, self.tenant)
        self.assertEqual(sale.seller, self.user)
        self.assertEqual(sale.status, "draft")

    def test_creation_avec_client(self):
        customer = make_customer(self.tenant)
        r = self.client.post(
            URL,
            {"location": str(self.location.id), "customer": str(customer.id)},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Sale.objects.first().customer, customer)

    def test_creation_sans_location_rejete(self):
        r = self.client.post(URL, {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_vendeur_injecte_depuis_request(self):
        r = self.client.post(URL, {"location": str(self.location.id)}, format="json")
        self.assertEqual(Sale.objects.get(id=r.data["data"]["id"]).seller, self.user)


class SaleRetrieveTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.sale = make_sale(self.tenant, self.user)

    def test_retrieve_ok(self):
        r = self.client.get(detail(self.sale.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("lines", r.data["data"])
        self.assertIn("payments", r.data["data"])

    def test_retrieve_autre_tenant_404(self):
        other = make_tenant("other")
        foreign = make_sale(other, self.user)
        r = self.client.get(detail(foreign.id))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class SaleUpdateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.location = make_location(self.tenant)
        self.sale = make_sale(self.tenant, self.user, location=self.location)

    def test_patch_channel(self):
        r = self.client.patch(detail(self.sale.id), {"channel": "whatsapp"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.channel, "whatsapp")

    def test_modification_vente_validee_interdite(self):
        self.sale.status = Sale.Status.VALIDATED
        self.sale.save()
        # Depuis l'état validated, même un patch doit être bloqué par Sale.save()
        r = self.client.patch(detail(self.sale.id), {"channel": "online"}, format="json")
        self.assertIn(r.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY])


class SaleDestroyTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.sale = make_sale(self.tenant, self.user)

    def test_suppression_draft_ok(self):
        r = self.client.delete(detail(self.sale.id))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Sale.objects.filter(id=self.sale.id).exists())


class SaleValidateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.sale = make_sale(self.tenant, self.user)

    def test_validation_depuis_draft(self):
        r = self.client.post(action_url(self.sale.id, "validate"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, "validated")
        self.assertIsNotNone(self.sale.validated_at)

    def test_validation_vente_deja_validee_rejete(self):
        self.sale.status = Sale.Status.VALIDATED
        self.sale.save()
        r = self.client.post(action_url(self.sale.id, "validate"))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validation_vente_annulee_rejete(self):
        self.sale.status = Sale.Status.CANCELLED
        # Sauvegarde directe (pas via save() qui bloque les validées)
        Sale.objects.filter(pk=self.sale.pk).update(status=Sale.Status.CANCELLED)
        r = self.client.post(action_url(self.sale.id, "validate"))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class SaleCancelTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.sale = make_sale(self.tenant, self.user)

    def test_annulation_draft_ok(self):
        r = self.client.post(action_url(self.sale.id, "cancel"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, "cancelled")

    def test_annulation_vente_validee_interdite(self):
        Sale.objects.filter(pk=self.sale.pk).update(status=Sale.Status.VALIDATED)
        r = self.client.post(action_url(self.sale.id, "cancel"))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_annulation_deja_annulee_rejete(self):
        Sale.objects.filter(pk=self.sale.pk).update(status=Sale.Status.CANCELLED)
        r = self.client.post(action_url(self.sale.id, "cancel"))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
