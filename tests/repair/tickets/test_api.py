"""
Tests d'intégration — Repair / RepairTicket.
Couvre : list, create, retrieve, update, destroy,
         actions transition et assign, isolation tenant.
"""
from django.utils import timezone
from rest_framework import status

from repair.models import RepairTicket, StatusHistory
from tests.factories import (
    TenantAPITestCase,
    make_customer,
    make_device,
    make_location,
    make_repair_ticket,
    make_tenant,
    make_user,
)

URL = "/api/v1/repair/tickets/"


def detail(pk):
    return f"{URL}{pk}/"


def action_url(pk, action):
    return f"{URL}{pk}/{action}/"


class RepairTicketListTest(TenantAPITestCase):

    def test_liste_vide(self):
        r = self.client.get(URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)

    def test_isolation_tenant(self):
        make_repair_ticket(self.tenant, self.user)
        other = make_tenant("other")
        make_repair_ticket(other, self.user)
        r = self.client.get(URL)
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)

    def test_filtre_par_status(self):
        make_repair_ticket(self.tenant, self.user)
        r = self.client.get(URL, {"status": "received"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 1)
        r = self.client.get(URL, {"status": "delivered"})
        self.assertEqual(r.data["data"]["pagination"]["total_items"], 0)

    def test_liste_sans_historique_imbrique(self):
        make_repair_ticket(self.tenant, self.user)
        r = self.client.get(URL)
        # La liste utilise RepairTicketListSerializer : pas de champ `history`
        self.assertNotIn("history", r.data["data"]["results"][0])


class RepairTicketCreateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.customer = make_customer(self.tenant)
        self.device = make_device(self.tenant, customer=self.customer)
        self.location = make_location(self.tenant)

    def test_creation_ok(self):
        payload = {
            "device": str(self.device.id),
            "customer": str(self.customer.id),
            "declared_issue": "Écran cassé",
            "location": str(self.location.id),
            "intake_at": timezone.now().isoformat(),
        }
        r = self.client.post(URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        ticket = RepairTicket.objects.get(id=r.data["data"]["id"])
        self.assertEqual(ticket.tenant, self.tenant)
        self.assertEqual(ticket.status, "received")
        self.assertIsNone(ticket.technician)

    def test_creation_sans_issue_rejete(self):
        payload = {
            "device": str(self.device.id),
            "customer": str(self.customer.id),
            "location": str(self.location.id),
            "intake_at": timezone.now().isoformat(),
        }
        r = self.client.post(URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)


class RepairTicketRetrieveTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.ticket = make_repair_ticket(self.tenant, self.user)

    def test_retrieve_contient_history(self):
        r = self.client.get(detail(self.ticket.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("history", r.data["data"])

    def test_retrieve_autre_tenant_404(self):
        other = make_tenant("other")
        foreign = make_repair_ticket(other, self.user)
        r = self.client.get(detail(foreign.id))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class RepairTicketUpdateTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.ticket = make_repair_ticket(self.tenant, self.user)

    def test_patch_declared_issue(self):
        r = self.client.patch(
            detail(self.ticket.id),
            {"declared_issue": "Batterie défectueuse"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.declared_issue, "Batterie défectueuse")


class RepairTicketDestroyTest(TenantAPITestCase):

    def test_suppression_ok(self):
        ticket = make_repair_ticket(self.tenant, self.user)
        r = self.client.delete(detail(ticket.id))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(RepairTicket.objects.filter(id=ticket.id).exists())


class RepairTicketTransitionTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.ticket = make_repair_ticket(self.tenant, self.user)

    def test_transition_valide(self):
        r = self.client.post(
            action_url(self.ticket.id, "transition"),
            {"to_status": "diagnosed", "note": "Carte mère HS"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, "diagnosed")

    def test_transition_cree_historique(self):
        self.client.post(
            action_url(self.ticket.id, "transition"),
            {"to_status": "diagnosed"},
            format="json",
        )
        self.assertEqual(StatusHistory.objects.filter(ticket=self.ticket).count(), 1)
        entry = StatusHistory.objects.get(ticket=self.ticket)
        self.assertEqual(entry.from_status, "received")
        self.assertEqual(entry.to_status, "diagnosed")
        self.assertEqual(entry.changed_by, self.user)

    def test_transition_illegale_rejete(self):
        # received → delivered est interdit
        r = self.client.post(
            action_url(self.ticket.id, "transition"),
            {"to_status": "delivered"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, "received")

    def test_transition_statut_terminal_rejete(self):
        RepairTicket.objects.filter(pk=self.ticket.pk).update(status="delivered")
        r = self.client.post(
            action_url(self.ticket.id, "transition"),
            {"to_status": "ready"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_historique_append_only_non_modifiable(self):
        self.client.post(
            action_url(self.ticket.id, "transition"),
            {"to_status": "diagnosed"},
            format="json",
        )
        entry = StatusHistory.objects.get(ticket=self.ticket)
        with self.assertRaises(Exception):
            entry.to_status = "hack"
            entry.save()


class RepairTicketAssignTest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.ticket = make_repair_ticket(self.tenant, self.user)
        self.technician = make_user(phone="+237690000050")

    def test_assignation_ok(self):
        r = self.client.post(
            action_url(self.ticket.id, "assign"),
            {"technician_id": str(self.technician.id)},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.technician, self.technician)

    def test_assignation_technicien_inexistant_404(self):
        r = self.client.post(
            action_url(self.ticket.id, "assign"),
            {"technician_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_historique_action(self):
        r = self.client.get(action_url(self.ticket.id, "history"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsInstance(r.data["data"], list)
