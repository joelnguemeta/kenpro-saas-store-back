"""
Tests du TenantMiddleware (résolution SaaS et on-premise).
On utilise RequestFactory pour forger des requêtes sans serveur HTTP.
"""
from django.test import RequestFactory, TestCase, override_settings

from accounts.models import Tenant
from accounts.tests.factories import make_tenant
from kenpro_store.middleware import TenantMiddleware


def _make_middleware():
    """Instancie le middleware avec une vue vide en bout de chaîne."""
    def dummy_view(request):
        from django.http import HttpResponse
        return HttpResponse("ok")
    return TenantMiddleware(dummy_view)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _request(host="localhost", path="/api/v1/accounts/users/", tenant_header=None):
    rf = RequestFactory()
    req = rf.get(path, HTTP_HOST=host)
    if tenant_header:
        req.META["HTTP_X_TENANT_SLUG"] = tenant_header
    return req


# ---------------------------------------------------------------------------
# Mode SaaS — résolution par sous-domaine
# ---------------------------------------------------------------------------

class TenantMiddlewareSaaSSubdomainTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant(name="Alice Shop", slug="alice")
        self.mw = _make_middleware()

    @override_settings(SINGLE_TENANT_SLUG="", TENANT_EXEMPT_PATHS=[])
    def test_sous_domaine_valide_injecte_tenant(self):
        req = _request(host="alice.kenpro.cm")
        self.mw(req)
        self.assertEqual(req.tenant, self.tenant)

    @override_settings(SINGLE_TENANT_SLUG="", TENANT_EXEMPT_PATHS=[])
    def test_sous_domaine_inconnu_retourne_404(self):
        req = _request(host="inconnu.kenpro.cm")
        resp = self.mw(req)
        self.assertEqual(resp.status_code, 404)

    @override_settings(SINGLE_TENANT_SLUG="", TENANT_EXEMPT_PATHS=[])
    def test_tenant_inactif_retourne_404(self):
        self.tenant.is_active = False
        self.tenant.save()
        req = _request(host="alice.kenpro.cm")
        resp = self.mw(req)
        self.assertEqual(resp.status_code, 404)

    @override_settings(SINGLE_TENANT_SLUG="", TENANT_EXEMPT_PATHS=[])
    def test_pas_de_sous_domaine_sans_header_retourne_404(self):
        req = _request(host="localhost")
        resp = self.mw(req)
        self.assertEqual(resp.status_code, 404)

    @override_settings(SINGLE_TENANT_SLUG="", TENANT_EXEMPT_PATHS=[])
    def test_reponse_404_est_json(self):
        req = _request(host="inconnu.kenpro.cm")
        resp = self.mw(req)
        self.assertIn("application/json", resp.get("Content-Type", ""))

    @override_settings(SINGLE_TENANT_SLUG="", TENANT_EXEMPT_PATHS=[])
    def test_host_avec_port_est_gere(self):
        req = _request(host="alice.kenpro.cm:8000")
        self.mw(req)
        self.assertEqual(req.tenant, self.tenant)


# ---------------------------------------------------------------------------
# Mode SaaS — fallback header X-Tenant-Slug (développement)
# ---------------------------------------------------------------------------

class TenantMiddlewareSaaSHeaderTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant(name="Bob Shop", slug="bob")
        self.mw = _make_middleware()

    @override_settings(SINGLE_TENANT_SLUG="", TENANT_EXEMPT_PATHS=[])
    def test_header_x_tenant_slug_injecte_tenant(self):
        req = _request(host="localhost", tenant_header="bob")
        self.mw(req)
        self.assertEqual(req.tenant, self.tenant)

    @override_settings(SINGLE_TENANT_SLUG="", TENANT_EXEMPT_PATHS=[])
    def test_header_inconnu_retourne_404(self):
        req = _request(host="localhost", tenant_header="inconnu")
        resp = self.mw(req)
        self.assertEqual(resp.status_code, 404)

    @override_settings(SINGLE_TENANT_SLUG="", TENANT_EXEMPT_PATHS=[])
    def test_sous_domaine_prioritaire_sur_header(self):
        """Le sous-domaine est résolu en priorité ; le header est ignoré s'il y a un sous-domaine."""
        other = make_tenant(name="Other", slug="other")
        req = _request(host="bob.kenpro.cm", tenant_header="other")
        self.mw(req)
        # Le tenant résolu doit être celui du sous-domaine, pas du header
        self.assertEqual(req.tenant, self.tenant)


# ---------------------------------------------------------------------------
# Mode on-premise (SINGLE_TENANT_SLUG renseigné)
# ---------------------------------------------------------------------------

class TenantMiddlewareOnPremiseTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant(name="Client Corp", slug="client-corp")
        self.mw = _make_middleware()

    @override_settings(SINGLE_TENANT_SLUG="client-corp", TENANT_EXEMPT_PATHS=[])
    def test_tenant_fixe_injecte_sur_toutes_les_requetes(self):
        for host in ["localhost", "127.0.0.1", "erp.client-corp.local"]:
            req = _request(host=host)
            self.mw(req)
            self.assertEqual(req.tenant, self.tenant, f"Échec pour host={host}")

    @override_settings(SINGLE_TENANT_SLUG="slug-inconnu", TENANT_EXEMPT_PATHS=[])
    def test_slug_onpremise_inconnu_retourne_404(self):
        req = _request(host="localhost")
        resp = self.mw(req)
        self.assertEqual(resp.status_code, 404)

    @override_settings(SINGLE_TENANT_SLUG="client-corp", TENANT_EXEMPT_PATHS=[])
    def test_tenant_inactif_onpremise_retourne_404(self):
        self.tenant.is_active = False
        self.tenant.save()
        req = _request(host="localhost")
        resp = self.mw(req)
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# Chemins exemptés
# ---------------------------------------------------------------------------

class TenantMiddlewareExemptPathsTest(TestCase):

    def setUp(self):
        self.mw = _make_middleware()

    @override_settings(SINGLE_TENANT_SLUG="", TENANT_EXEMPT_PATHS=["/admin/", "/api/v1/accounts/register/"])
    def test_chemin_exempte_ne_resout_pas_le_tenant(self):
        for path in ["/admin/", "/admin/login/", "/api/v1/accounts/register/"]:
            req = _request(host="localhost", path=path)
            resp = self.mw(req)
            self.assertEqual(resp.status_code, 200, f"Devrait passer pour {path}")
            self.assertIsNone(req.tenant, f"tenant devrait être None pour {path}")

    @override_settings(SINGLE_TENANT_SLUG="", TENANT_EXEMPT_PATHS=["/admin/"])
    def test_chemin_non_exempte_exige_tenant(self):
        req = _request(host="localhost", path="/api/v1/accounts/users/")
        resp = self.mw(req)
        self.assertEqual(resp.status_code, 404)
