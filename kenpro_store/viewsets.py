"""
Bases de viewsets partagées par les apps métier (inventory, sales, promotions).

Le multi-tenant impose deux règles sur chaque ressource appartenant à un
tenant : ne jamais exposer les données d'une autre boutique, et rattacher
automatiquement les créations au tenant actif (résolu par TenantMiddleware
dans request.tenant).
"""
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied

from kenpro_store.enums import SuccessMessage
from kenpro_store.responses import SuccessResponse


class _SuccessResponseMixin:
    """Surcharge les méthodes DRF standard pour retourner SuccessResponse."""

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return SuccessResponse(data=self.get_serializer(qs, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return SuccessResponse(data=self.get_serializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return SuccessResponse(
            data=serializer.data,
            message=SuccessMessage.CREATED,
            status_code=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return SuccessResponse(data=serializer.data, message=SuccessMessage.UPDATED)

    def destroy(self, request, *args, **kwargs):
        self.perform_destroy(self.get_object())
        return SuccessResponse(message=SuccessMessage.DELETED, status_code=status.HTTP_204_NO_CONTENT)


class TenantScopedViewSet(_SuccessResponseMixin, viewsets.ModelViewSet):
    """
    ViewSet filtrant systématiquement sur le tenant actif et injectant ce
    tenant à la création. Suppose un modèle portant un champ `tenant`
    (cf. kenpro_store.db.TenantOwnedModel).
    """

    def _require_tenant(self):
        tenant = getattr(self.request, "tenant", None)
        if tenant is None:
            raise PermissionDenied("Aucun tenant actif sur la requête.")
        return tenant

    def get_queryset(self):
        return super().get_queryset().filter(tenant=self._require_tenant())

    def perform_create(self, serializer):
        serializer.save(tenant=self._require_tenant())


class TenantScopedReadOnlyViewSet(_SuccessResponseMixin, viewsets.ReadOnlyModelViewSet):
    """Variante lecture seule — pour les caches recalculables (ex. StockLevel)."""

    def _require_tenant(self):
        tenant = getattr(self.request, "tenant", None)
        if tenant is None:
            raise PermissionDenied("Aucun tenant actif sur la requête.")
        return tenant

    def get_queryset(self):
        return super().get_queryset().filter(tenant=self._require_tenant())
