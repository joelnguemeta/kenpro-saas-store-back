"""
Viewsets de l'app `sales`.

Cycle de vie d'une vente :
  draft → validated (immuable) ou cancelled.

Actions supplémentaires :
  - POST /tickets/{id}/validate/  → passe en 'validated'
  - POST /tickets/{id}/cancel/    → passe en 'cancelled'

Les lignes et paiements sont gérés via leurs propres endpoints CRUD,
filtrés par vente via le query param `sale`.
"""
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from kenpro_store.enums import ErrorCode, SuccessMessage
from kenpro_store.responses import ErrorResponse, SuccessResponse
from kenpro_store.viewsets import TenantScopedViewSet

from crm.services import DebtService

from .models import Payment, Sale, SaleLine
from .serializers import (
    CancelSaleSerializer,
    PaymentSerializer,
    SaleLineSerializer,
    SaleListSerializer,
    SaleSerializer,
    ValidateSaleSerializer,
)

_TAG = "Ventes"


@extend_schema_view(
    list=extend_schema(summary="Lister les ventes", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'une vente", tags=[_TAG]),
    create=extend_schema(summary="Ouvrir une vente (draft)", tags=[_TAG]),
    update=extend_schema(summary="Modifier une vente", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier une vente (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer une vente", tags=[_TAG]),
)
class SaleViewSet(TenantScopedViewSet):
    # Attribut de classe requis par drf-spectacular pour inférer le type du pk (UUID).
    queryset = Sale.objects.none()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["reference", "customer__name", "seller__username"]
    ordering_fields = ["created_at", "validated_at", "total"]

    def get_queryset(self):
        qs = Sale.objects.select_related(
            "customer", "seller", "location"
        ).prefetch_related("lines", "payments")
        qs = qs.filter(tenant=self._require_tenant())
        params = self.request.query_params
        for field in ("status", "channel", "location", "seller"):
            if field in params:
                qs = qs.filter(**{field: params[field]})
        return qs.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "list":
            return SaleListSerializer
        return SaleSerializer

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return SuccessResponse(data=self.get_serializer(qs, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return SuccessResponse(data=self.get_serializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Injecte le vendeur en plus du tenant
        serializer.save(tenant=self._require_tenant(), seller=request.user)
        full = SaleSerializer(serializer.instance, context=self.get_serializer_context())
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

    # --- Actions métier ---

    @extend_schema(
        summary="Valider une vente",
        description="Passe le statut en 'validated'. La vente devient immuable.",
        request=ValidateSaleSerializer,
        tags=[_TAG],
    )
    @action(detail=True, methods=["post"], url_path="validate")
    def validate_sale(self, request, pk=None):
        sale = self.get_object()

        if sale.status != Sale.Status.DRAFT:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message=f"Seule une vente en 'draft' peut être validée (statut actuel : '{sale.status}').",
            )

        # La règle d'immuabilité est gérée dans Sale.save() — on change ici
        # depuis draft, donc ça passe.
        sale.status = Sale.Status.VALIDATED
        sale.save()

        full = SaleSerializer(sale, context=self.get_serializer_context())
        return SuccessResponse(data=full.data, message="Vente validée.")

    @extend_schema(
        summary="Annuler une vente",
        description="Passe le statut en 'cancelled'. Impossible si déjà validée.",
        request=CancelSaleSerializer,
        tags=[_TAG],
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel_sale(self, request, pk=None):
        sale = self.get_object()

        if sale.status == Sale.Status.VALIDATED:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message="Une vente validée ne peut pas être annulée. Créez un avoir.",
            )
        if sale.status == Sale.Status.CANCELLED:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message="La vente est déjà annulée.",
            )

        sale.status = Sale.Status.CANCELLED
        sale.save()

        full = SaleSerializer(sale, context=self.get_serializer_context())
        return SuccessResponse(data=full.data, message="Vente annulée.")


@extend_schema_view(
    list=extend_schema(summary="Lister les lignes de vente", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'une ligne", tags=[_TAG]),
    create=extend_schema(summary="Ajouter une ligne à une vente", tags=[_TAG]),
    update=extend_schema(summary="Modifier une ligne", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier une ligne (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer une ligne", tags=[_TAG]),
)
class SaleLineViewSet(TenantScopedViewSet):
    queryset = SaleLine.objects.none()
    serializer_class = SaleLineSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        qs = SaleLine.objects.select_related("sale", "product").filter(
            tenant=self._require_tenant()
        )
        # Filtrage optionnel par vente (?sale=<uuid>)
        sale_id = self.request.query_params.get("sale")
        if sale_id:
            qs = qs.filter(sale=sale_id)
        return qs.order_by("created_at")

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return SuccessResponse(data=self.get_serializer(qs, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return SuccessResponse(data=self.get_serializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Injecte adjusted_by si une remise est appliquée
        adj = serializer.validated_data.get("line_adjustment", 0)
        extra = {"adjusted_by": request.user} if adj else {}
        try:
            serializer.save(tenant=self._require_tenant(), **extra)
        except Exception as exc:
            raise ValidationError({"detail": str(exc)})
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


@extend_schema_view(
    list=extend_schema(summary="Lister les paiements d'une vente", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'un paiement", tags=[_TAG]),
    create=extend_schema(summary="Enregistrer un paiement", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer un paiement", tags=[_TAG]),
)
class PaymentViewSet(TenantScopedViewSet):
    """
    Les paiements ne sont pas modifiables après création.
    PUT/PATCH sont désactivés (http_method_names).
    """
    queryset = Payment.objects.none()
    serializer_class = PaymentSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        qs = Payment.objects.select_related("sale", "recorded_by").filter(
            tenant=self._require_tenant()
        )
        sale_id = self.request.query_params.get("sale")
        if sale_id:
            qs = qs.filter(sale=sale_id)
        return qs.order_by("created_at")

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return SuccessResponse(data=self.get_serializer(qs, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return SuccessResponse(data=self.get_serializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save(tenant=self._require_tenant(), recorded_by=request.user)

        # Un paiement CREDIT impute la dette au client lié à la vente.
        if payment.method == Payment.Method.CREDIT and payment.sale.customer_id:
            customer = payment.sale.customer
            DebtService.charge(
                customer,
                payment.amount,
                reference=str(payment.sale_id),
                recorded_by=request.user,
            )

        return SuccessResponse(
            data=serializer.data,
            message=SuccessMessage.CREATED,
            status_code=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        self.perform_destroy(self.get_object())
        return SuccessResponse(message=SuccessMessage.DELETED, status_code=status.HTTP_204_NO_CONTENT)
