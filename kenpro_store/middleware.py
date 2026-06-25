"""
Résolution du tenant courant sur chaque requête.

Deux modes contrôlés par la variable d'environnement SINGLE_TENANT_SLUG :

  - Vide (défaut) → mode SaaS :
      Le slug est extrait du sous-domaine : alice.kenpro.cm → "alice".
      En l'absence de sous-domaine (localhost, IP), on se rabat sur
      l'en-tête HTTP X-Tenant-Slug (utile en développement et pour les tests).

  - Renseigné → mode on-premise :
      Un seul tenant, identifié par ce slug, est injecté sur toutes les
      requêtes. Aucune résolution dynamique.

Dans les deux cas, request.tenant est disponible dans toutes les vues
et services en aval. Les chemins listés dans TENANT_EXEMPT_PATHS sont
ignorés (admin Django, schéma OpenAPI, inscription).
"""
import json
import os

from django.conf import settings
from django.http import HttpResponse

from accounts.models import Tenant


class TenantMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_exempt(request.path):
            request.tenant = None
            return self.get_response(request)

        tenant = self._resolve(request)
        if tenant is None:
            return self._not_found(request)

        request.tenant = tenant
        return self.get_response(request)

    # ------------------------------------------------------------------

    def _is_exempt(self, path: str) -> bool:
        exempt_paths: list[str] = getattr(settings, "TENANT_EXEMPT_PATHS", [])
        return any(path.startswith(p) for p in exempt_paths)

    def _resolve(self, request) -> Tenant | None:
        # Lu à chaque requête pour que override_settings fonctionne en tests
        single_slug: str = getattr(settings, "SINGLE_TENANT_SLUG", "") or ""
        if single_slug:
            return self._get_tenant(single_slug)
        return self._resolve_saas(request)

    def _resolve_saas(self, request) -> Tenant | None:
        slug = self._slug_from_subdomain(request)
        if not slug:
            # Fallback développement : en-tête X-Tenant-Slug
            slug = request.META.get("HTTP_X_TENANT_SLUG", "").strip()
        if not slug:
            return None
        return self._get_tenant(slug)

    @staticmethod
    def _slug_from_subdomain(request) -> str:
        """
        Extrait le premier segment du host.
        "alice.kenpro.cm" → "alice"
        "localhost" ou "127.0.0.1" → "" (pas de sous-domaine)
        """
        host = request.META.get("HTTP_HOST", "").split(":")[0]   # retire le port si présent
        parts = host.split(".")
        # Un seul segment = localhost ou IP → pas de sous-domaine
        if len(parts) <= 1:
            return ""
        # Vérifie que le premier segment n'est pas une IP (ex: 127.0.0.1 → ["127","0","0","1"])
        if parts[0].isdigit():
            return ""
        return parts[0]

    @staticmethod
    def _get_tenant(slug: str) -> Tenant | None:
        try:
            return Tenant.objects.get(slug=slug, is_active=True)
        except Tenant.DoesNotExist:
            return None

    @staticmethod
    def _not_found(request) -> HttpResponse:
        body = json.dumps({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": "Tenant introuvable ou inactif.",
            },
        })
        return HttpResponse(body, status=404, content_type="application/json")
