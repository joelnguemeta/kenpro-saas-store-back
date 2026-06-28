"""
Viewsets de l'app `supplier`.

Particularités :
  - Supplier est global (pas de tenant) → viewset standard sans TenantScopedViewSet.
  - SupplierLink, CreditStatement, CreditEntry, CreditPayment sont tenant-scopés.
  - CreditEntry est append-only (POST + GET uniquement).
  - CreditPayment expose une action `confirm` pour passer de 'declared' à 'confirmed'.
"""
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, status, viewsets
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.decorators import action

from kenpro_store.enums import ErrorCode, SuccessMessage
from kenpro_store.responses import ErrorResponse, SuccessResponse
from kenpro_store.viewsets import TenantScopedViewSet

from .models import CreditEntry, CreditPayment, CreditStatement, Supplier, SupplierLink
from .serializers import (
    ConfirmPaymentSerializer,
    CreditEntrySerializer,
    CreditPaymentSerializer,
    CreditStatementListSerializer,
    CreditStatementSerializer,
    SupplierLinkSerializer,
    SupplierSerializer,
)

_TAG = "Fournisseurs"
_CREDIT_TAG = "Crédit fournisseur"


# ---------------------------------------------------------------------------
# Fournisseur global (sans tenant)
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="Lister les fournisseurs", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'un fournisseur", tags=[_TAG]),
    create=extend_schema(summary="Créer un fournisseur", tags=[_TAG]),
    update=extend_schema(summary="Modifier un fournisseur", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier un fournisseur (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer un fournisseur", tags=[_TAG]),
)
class SupplierViewSet(viewsets.ModelViewSet):
    """Entité globale — non filtrée par tenant."""
    queryset = Supplier.objects.order_by("name")
    serializer_class = SupplierSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "email"]
    ordering_fields = ["name", "created_at"]

    def get_permissions(self):
        # Read-only for any authenticated user; mutations require staff.
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAdminUser()]

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


# ---------------------------------------------------------------------------
# Lien boutique × fournisseur
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="Lister les liens fournisseurs de la boutique", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'un lien fournisseur", tags=[_TAG]),
    create=extend_schema(summary="Relier un fournisseur à la boutique", tags=[_TAG]),
    update=extend_schema(summary="Modifier le plafond de crédit", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier un lien (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer un lien fournisseur", tags=[_TAG]),
)
class SupplierLinkViewSet(TenantScopedViewSet):
    queryset = SupplierLink.objects.select_related("supplier").order_by("supplier__name")
    serializer_class = SupplierLinkSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["supplier__name"]

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


# ---------------------------------------------------------------------------
# Relevé de crédit
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="Lister les relevés de crédit", tags=[_CREDIT_TAG]),
    retrieve=extend_schema(summary="Détail d'un relevé (avec écritures et paiements)", tags=[_CREDIT_TAG]),
    create=extend_schema(summary="Ouvrir un relevé de crédit", tags=[_CREDIT_TAG]),
    update=extend_schema(summary="Modifier un relevé", tags=[_CREDIT_TAG]),
    partial_update=extend_schema(summary="Modifier un relevé (partiel)", tags=[_CREDIT_TAG]),
    destroy=extend_schema(summary="Supprimer un relevé", tags=[_CREDIT_TAG]),
)
class CreditStatementViewSet(TenantScopedViewSet):
    queryset = CreditStatement.objects.none()
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "balance"]

    def get_queryset(self):
        qs = CreditStatement.objects.select_related("supplier_link__supplier").prefetch_related(
            "entries", "payments"
        ).filter(tenant=self._require_tenant())
        # Filtrage optionnel par lien ou statut
        params = self.request.query_params
        for field in ("supplier_link", "status"):
            if field in params:
                qs = qs.filter(**{field: params[field]})
        return qs.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "list":
            return CreditStatementListSerializer
        return CreditStatementSerializer

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
        full = CreditStatementSerializer(serializer.instance, context=self.get_serializer_context())
        return SuccessResponse(
            data=full.data,
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


# ---------------------------------------------------------------------------
# Écriture de crédit (append-only)
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="Lister les écritures de crédit", tags=[_CREDIT_TAG]),
    retrieve=extend_schema(summary="Détail d'une écriture", tags=[_CREDIT_TAG]),
    create=extend_schema(
        summary="Créer une écriture de crédit",
        description="Append-only : aucune modification ni suppression possible.",
        tags=[_CREDIT_TAG],
    ),
)
class CreditEntryViewSet(TenantScopedViewSet):
    """POST + GET uniquement — append-only."""
    queryset = CreditEntry.objects.none()
    serializer_class = CreditEntrySerializer
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        qs = CreditEntry.objects.select_related("statement", "created_by").filter(
            statement__tenant=self._require_tenant()
        )
        statement_id = self.request.query_params.get("statement")
        if statement_id:
            qs = qs.filter(statement=statement_id)
        return qs.order_by("created_at")

    # CreditEntry n'a pas de champ tenant propre — on l'exclut de perform_create
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

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


# ---------------------------------------------------------------------------
# Paiement fournisseur
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="Lister les paiements fournisseur", tags=[_CREDIT_TAG]),
    retrieve=extend_schema(summary="Détail d'un paiement fournisseur", tags=[_CREDIT_TAG]),
    create=extend_schema(summary="Déclarer un paiement fournisseur", tags=[_CREDIT_TAG]),
    destroy=extend_schema(summary="Supprimer un paiement non confirmé", tags=[_CREDIT_TAG]),
)
class CreditPaymentViewSet(TenantScopedViewSet):
    """POST + GET + DELETE. PUT/PATCH désactivés."""
    queryset = CreditPayment.objects.none()
    serializer_class = CreditPaymentSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        qs = CreditPayment.objects.select_related("statement", "recorded_by").filter(
            statement__tenant=self._require_tenant()
        )
        statement_id = self.request.query_params.get("statement")
        if statement_id:
            qs = qs.filter(statement=statement_id)
        return qs.order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)

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

    def destroy(self, request, *args, **kwargs):
        payment = self.get_object()
        if payment.status == CreditPayment.Status.CONFIRMED:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message="Un paiement confirmé ne peut pas être supprimé.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        self.perform_destroy(payment)
        return SuccessResponse(message=SuccessMessage.DELETED, status_code=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Confirmer un paiement fournisseur",
        description="Passe le statut de 'declared' à 'confirmed'.",
        request=ConfirmPaymentSerializer,
        tags=[_CREDIT_TAG],
    )
    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        payment = self.get_object()
        if payment.status == CreditPayment.Status.CONFIRMED:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message="Ce paiement est déjà confirmé.",
            )
        payment.status = CreditPayment.Status.CONFIRMED
        payment.save()
        return SuccessResponse(
            data=CreditPaymentSerializer(payment, context=self.get_serializer_context()).data,
            message="Paiement confirmé.",
        )
