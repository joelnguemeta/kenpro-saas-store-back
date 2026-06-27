"""
Tests d'intégration API (accounts/views.py).
Chaque test fait de vraies requêtes HTTP via le client DRF et vérifie
le statut HTTP, la structure JSON et l'état de la base de données.

Toutes les classes héritent de TenantAPITestCase qui injecte automatiquement
le header X-Tenant-Slug pour satisfaire le TenantMiddleware.
"""
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status

from accounts.models import Membership, PinScope, Role, Tenant, User
from accounts.services import MembershipService

from .factories import (
    TenantAPITestCase,
    get_any_permission,
    make_membership,
    make_role,
    make_tenant,
    make_user,
)

REGISTER_URL = "/api/v1/accounts/register/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def url_list(basename):
    return reverse(f"{basename}-list")


def url_detail(basename, pk):
    return reverse(f"{basename}-detail", kwargs={"pk": str(pk)})


def url_action(basename, pk, action):
    return reverse(f"{basename}-{action}", kwargs={"pk": str(pk)})


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

class RegisterAPITest(TenantAPITestCase):

    def test_inscription_minimale(self):
        r = self.client.post(REGISTER_URL, {"phone": "+237600000001"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["phone"], "+237600000001")
        self.assertNotIn("password", r.data)
        self.assertTrue(User.objects.filter(phone="+237600000001").exists())

    def test_inscription_complete(self):
        payload = {
            "phone": "+237600000002",
            "full_name": "Alice Mbida",
            "email": "alice@example.com",
            "password": "motdepasse123",
        }
        r = self.client.post(REGISTER_URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(phone="+237600000002")
        self.assertEqual(user.full_name, "Alice Mbida")
        self.assertTrue(user.check_password("motdepasse123"))

    def test_sans_mot_de_passe_set_unusable(self):
        self.client.post(REGISTER_URL, {"phone": "+237600000003"}, format="json")
        user = User.objects.get(phone="+237600000003")
        self.assertFalse(user.has_usable_password())

    def test_phone_duplique_rejete(self):
        make_user(phone="+237600000004")
        r = self.client.post(REGISTER_URL, {"phone": "+237600000004"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sans_phone_rejete(self):
        r = self.client.post(REGISTER_URL, {"full_name": "Bob"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mot_de_passe_trop_court_rejete(self):
        payload = {"phone": "+237600000005", "password": "123"}
        r = self.client.post(REGISTER_URL, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reponse_ne_contient_pas_le_hash_password(self):
        r = self.client.post(REGISTER_URL, {"phone": "+237600000006", "password": "secret123"}, format="json")
        self.assertNotIn("password", r.data)
        self.assertNotIn("pin", r.data)

    def test_user_actif_par_defaut(self):
        self.client.post(REGISTER_URL, {"phone": "+237600000007"}, format="json")
        user = User.objects.get(phone="+237600000007")
        self.assertTrue(user.is_active)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserListCreateAPITest(TenantAPITestCase):

    def test_lister_utilisateurs_vide(self):
        r = self.client.get(url_list("user"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], 0)

    def test_creer_utilisateur_sans_mot_de_passe(self):
        payload = {"phone": "+237600000001"}
        r = self.client.post(url_list("user"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["phone"], "+237600000001")
        self.assertNotIn("password", r.data)
        self.assertTrue(User.objects.filter(phone="+237600000001").exists())

    def test_creer_utilisateur_avec_mot_de_passe(self):
        payload = {"phone": "+237600000002", "password": "secret123"}
        r = self.client.post(url_list("user"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(phone="+237600000002")
        self.assertTrue(user.check_password("secret123"))

    def test_creer_utilisateur_phone_duplique(self):
        make_user(phone="+237600000003")
        r = self.client.post(url_list("user"), {"phone": "+237600000003"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creer_utilisateur_sans_phone_rejete(self):
        r = self.client.post(url_list("user"), {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class UserDetailAPITest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.user = make_user(phone="+237600000010", full_name="Alice")

    def test_recuperer_utilisateur(self):
        r = self.client.get(url_detail("user", self.user.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["phone"], "+237600000010")
        self.assertEqual(r.data["full_name"], "Alice")

    def test_modifier_utilisateur_partiel(self):
        r = self.client.patch(url_detail("user", self.user.pk), {"full_name": "Alice B."}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Alice B.")

    def test_supprimer_utilisateur(self):
        r = self.client.delete(url_detail("user", self.user.pk))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_utilisateur_introuvable(self):
        import uuid
        r = self.client.get(url_detail("user", uuid.uuid4()))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------

class TenantAPITest(TenantAPITestCase):

    def test_creer_tenant(self):
        payload = {"name": "Kenpro Shop", "slug": "kenpro-shop", "country": "CM", "currency": "XAF"}
        r = self.client.post(url_list("tenant"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Tenant.objects.filter(slug="kenpro-shop").exists())

    def test_lister_tenants(self):
        # self.tenant créé par TenantAPITestCase + 2 autres
        make_tenant(slug="t1")
        make_tenant(name="Autre", slug="t2")
        r = self.client.get(url_list("tenant"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], 3)  # test-tenant + t1 + t2

    def test_recuperer_tenant(self):
        r = self.client.get(url_detail("tenant", self.tenant.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["slug"], self.tenant.slug)

    def test_modifier_tenant(self):
        r = self.client.patch(url_detail("tenant", self.tenant.pk), {"name": "Nouveau nom"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.name, "Nouveau nom")

    def test_supprimer_tenant(self):
        t = make_tenant(slug="a-supprimer")
        r = self.client.delete(url_detail("tenant", t.pk))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)

    def test_slug_duplique_rejete(self):
        payload = {"name": "Autre", "slug": self.tenant_slug, "country": "SN", "currency": "XOF"}
        r = self.client.post(url_list("tenant"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

class RoleAPITest(TenantAPITestCase):

    def test_creer_role_avec_tenant(self):
        payload = {"name": "Caissier", "tenant": str(self.tenant.pk)}
        r = self.client.post(url_list("role"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["name"], "Caissier")

    def test_creer_role_systeme_global(self):
        payload = {"name": "SuperAdmin", "is_system": True}
        r = self.client.post(url_list("role"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(r.data["tenant"])

    def test_role_contient_is_expired(self):
        role = make_role(tenant=self.tenant)
        r = self.client.get(url_detail("role", role.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("is_expired", r.data)
        self.assertFalse(r.data["is_expired"])

    def test_role_contient_permissions(self):
        role = make_role(tenant=self.tenant)
        r = self.client.get(url_detail("role", role.pk))
        self.assertIn("role_permissions", r.data)
        self.assertIsInstance(r.data["role_permissions"], list)

    def test_nom_duplique_meme_tenant_rejete(self):
        make_role(name="Vendeur", tenant=self.tenant)
        r = self.client.post(url_list("role"), {"name": "Vendeur", "tenant": str(self.tenant.pk)}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_meme_nom_tenants_differents_accepte(self):
        tenant2 = make_tenant(name="Autre", slug="autre")
        make_role(name="Vendeur", tenant=self.tenant)
        r = self.client.post(url_list("role"), {"name": "Vendeur", "tenant": str(tenant2.pk)}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_supprimer_role(self):
        role = make_role(tenant=self.tenant)
        r = self.client.delete(url_detail("role", role.pk))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------

class MembershipAPITest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.user = make_user()
        self.role = make_role(tenant=self.tenant)

    def test_creer_membership(self):
        payload = {
            "user": str(self.user.pk),
            "tenant": str(self.tenant.pk),
            "role": str(self.role.pk),
        }
        r = self.client.post(url_list("membership"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertFalse(r.data["has_pin"])
        self.assertFalse(r.data["is_expired"])

    def test_lister_memberships(self):
        Membership.objects.create(user=self.user, tenant=self.tenant, role=self.role)
        r = self.client.get(url_list("membership"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], 1)

    def test_membership_duplique_rejete(self):
        Membership.objects.create(user=self.user, tenant=self.tenant, role=self.role)
        payload = {"user": str(self.user.pk), "tenant": str(self.tenant.pk), "role": str(self.role.pk)}
        r = self.client.post(url_list("membership"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class MembershipPinAPITest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.membership = make_membership(tenant=self.tenant)
        self.set_pin_url = url_action("membership", self.membership.pk, "set-pin")
        self.clear_pin_url = url_action("membership", self.membership.pk, "clear-pin")
        self.verify_pin_url = url_action("membership", self.membership.pk, "verify-pin")

    def test_set_pin_valide(self):
        r = self.client.post(self.set_pin_url, {"pin": "4829"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.has_pin)

    def test_set_pin_trop_court(self):
        r = self.client.post(self.set_pin_url, {"pin": "12"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_set_pin_absent(self):
        r = self.client.post(self.set_pin_url, {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_pin_correct(self):
        self.client.post(self.set_pin_url, {"pin": "4829"}, format="json")
        r = self.client.post(self.verify_pin_url, {"pin": "4829"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_verify_pin_incorrect(self):
        self.client.post(self.set_pin_url, {"pin": "4829"}, format="json")
        r = self.client.post(self.verify_pin_url, {"pin": "0000"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_verify_pin_sans_pin_defini(self):
        r = self.client.post(self.verify_pin_url, {"pin": "1234"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_clear_pin(self):
        self.client.post(self.set_pin_url, {"pin": "4829"}, format="json")
        r = self.client.post(self.clear_pin_url, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.membership.refresh_from_db()
        self.assertIsNone(self.membership.pin)

    def test_set_pin_membership_inexistant(self):
        import uuid
        r = self.client.post(
            url_action("membership", uuid.uuid4(), "set-pin"),
            {"pin": "1234"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_pin_non_expose_dans_la_liste(self):
        """Le hash du PIN ne doit jamais apparaître dans les réponses de l'API."""
        MembershipService.set_pin(self.membership, "9999")
        r = self.client.get(url_list("membership"))
        data = r.data["results"][0]
        self.assertNotIn("pin", data)
        self.assertIn("has_pin", data)
        self.assertTrue(data["has_pin"])


PASSWORD_RESET_REQUEST_URL = "/api/v1/accounts/password-reset/request/"
PASSWORD_RESET_CONFIRM_URL = "/api/v1/accounts/password-reset/confirm/"
PASSWORD_CHANGE_URL = "/api/v1/accounts/password/change/"
PIN_RESET_REQUEST_URL = "/api/v1/accounts/pin-reset/request/"
PIN_RESET_CONFIRM_URL = "/api/v1/accounts/pin-reset/confirm/"


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------

class PasswordResetAPITest(TenantAPITestCase):

    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    def setUp(self):
        super().setUp()
        self.user = make_user(phone="+237600000080")
        self.user.email = "reset@example.com"
        self.user.set_password("ancienMotDePasse")
        self.user.save()

    def test_request_reset_envoie_email(self):
        from django.core import mail
        with self.settings(EMAIL_BACKEND=self.EMAIL_BACKEND):
            r = self.client.post(PASSWORD_RESET_REQUEST_URL, {"email": "reset@example.com"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_request_reset_email_inconnu(self):
        r = self.client.post(PASSWORD_RESET_REQUEST_URL, {"email": "inconnu@example.com"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_request_reset_email_manquant(self):
        r = self.client.post(PASSWORD_RESET_REQUEST_URL, {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_reset_applique_nouveau_mot_de_passe(self):
        from accounts.services import PasswordResetService
        with self.settings(EMAIL_BACKEND=self.EMAIL_BACKEND):
            _, raw = PasswordResetService.request_reset("reset@example.com")
        r = self.client.post(
            PASSWORD_RESET_CONFIRM_URL,
            {"token": raw, "new_password": "nouveauMotDePasse123"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("nouveauMotDePasse123"))

    def test_confirm_reset_jeton_invalide(self):
        r = self.client.post(
            PASSWORD_RESET_CONFIRM_URL,
            {"token": "faux-jeton", "new_password": "nouveauMotDePasse123"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_reset_nouveau_mot_de_passe_trop_court(self):
        r = self.client.post(
            PASSWORD_RESET_CONFIRM_URL,
            {"token": "peu-importe", "new_password": "court"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class PasswordChangeAPITest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.user = make_user(phone="+237600000090")
        self.user.set_password("ancienMotDePasse")
        self.user.save()

    def test_changer_mot_de_passe(self):
        r = self.client.post(
            PASSWORD_CHANGE_URL,
            {"phone": "+237600000090", "current_password": "ancienMotDePasse", "new_password": "nouveauMotDePasse123"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("nouveauMotDePasse123"))

    def test_mot_de_passe_actuel_incorrect(self):
        r = self.client.post(
            PASSWORD_CHANGE_URL,
            {"phone": "+237600000090", "current_password": "mauvais", "new_password": "nouveauMotDePasse123"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_utilisateur_introuvable(self):
        r = self.client.post(
            PASSWORD_CHANGE_URL,
            {"phone": "+237699999999", "current_password": "x", "new_password": "nouveauMotDePasse123"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_compte_otp_rejete(self):
        user_otp = make_user(phone="+237600000091")  # sans password
        r = self.client.post(
            PASSWORD_CHANGE_URL,
            {"phone": "+237600000091", "current_password": "", "new_password": "nouveauMotDePasse123"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nouveau_mot_de_passe_trop_court(self):
        r = self.client.post(
            PASSWORD_CHANGE_URL,
            {"phone": "+237600000090", "current_password": "ancienMotDePasse", "new_password": "court"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Pin Reset
# ---------------------------------------------------------------------------

class PinResetAPITest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.membership = make_membership(tenant=self.tenant)
        self.membership.user.email = "alice@example.com"
        self.membership.user.save()

    def test_request_reset_envoie_email(self):
        from django.core import mail
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            r = self.client.post(
                PIN_RESET_REQUEST_URL,
                {"membership_id": str(self.membership.pk)},
                format="json",
            )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("alice@example.com", mail.outbox[0].to)

    def test_request_reset_membership_inconnu(self):
        import uuid
        r = self.client.post(
            PIN_RESET_REQUEST_URL,
            {"membership_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_request_reset_sans_email_rejete(self):
        self.membership.user.email = None
        self.membership.user.save()
        r = self.client.post(
            PIN_RESET_REQUEST_URL,
            {"membership_id": str(self.membership.pk)},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_reset_nouveau_pin_applique(self):
        from accounts.services import PinResetService
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            _, raw = PinResetService.request_reset(self.membership)
        r = self.client.post(
            PIN_RESET_CONFIRM_URL,
            {"token": raw, "new_pin": "9182"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.membership.refresh_from_db()
        from accounts.services import MembershipService
        self.assertTrue(MembershipService.verify_pin(self.membership, "9182"))

    def test_confirm_reset_jeton_invalide(self):
        r = self.client.post(
            PIN_RESET_CONFIRM_URL,
            {"token": "faux-jeton", "new_pin": "1234"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_reset_nouveau_pin_trop_court(self):
        r = self.client.post(
            PIN_RESET_CONFIRM_URL,
            {"token": "peu-importe", "new_pin": "12"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# PinScopes
# ---------------------------------------------------------------------------

class PinScopeAPITest(TenantAPITestCase):

    def setUp(self):
        super().setUp()
        self.ct = ContentType.objects.get_for_model(Role)

    def test_creer_pin_scope(self):
        payload = {
            "tenant": str(self.tenant.pk),
            "content_type": self.ct.pk,
            "label": "Gestion des rôles",
        }
        r = self.client.post(url_list("pinscope"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(PinScope.objects.filter(tenant=self.tenant, content_type=self.ct).exists())

    def test_creer_pin_scope_contient_label_content_type(self):
        payload = {"tenant": str(self.tenant.pk), "content_type": self.ct.pk, "label": "Test"}
        r = self.client.post(url_list("pinscope"), payload, format="json")
        self.assertIn("content_type_label", r.data)
        self.assertIsInstance(r.data["content_type_label"], str)

    def test_doublon_tenant_content_type_rejete(self):
        PinScope.objects.create(tenant=self.tenant, content_type=self.ct)
        payload = {"tenant": str(self.tenant.pk), "content_type": self.ct.pk}
        r = self.client.post(url_list("pinscope"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_lister_pin_scopes(self):
        PinScope.objects.create(tenant=self.tenant, content_type=self.ct)
        r = self.client.get(url_list("pinscope"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["count"], 1)

    def test_supprimer_pin_scope(self):
        scope = PinScope.objects.create(tenant=self.tenant, content_type=self.ct)
        r = self.client.delete(url_detail("pinscope", scope.pk))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PinScope.objects.filter(pk=scope.pk).exists())

    def test_meme_content_type_tenants_differents_accepte(self):
        tenant2 = make_tenant(name="Autre", slug="autre")
        PinScope.objects.create(tenant=self.tenant, content_type=self.ct)
        payload = {"tenant": str(tenant2.pk), "content_type": self.ct.pk}
        r = self.client.post(url_list("pinscope"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
