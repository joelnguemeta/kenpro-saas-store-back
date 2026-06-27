"""
Viewsets de l'app `crm`.
"""
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from kenpro_store.enums import SuccessMessage
from kenpro_store.responses import SuccessResponse
from kenpro_store.viewsets import TenantScopedViewSet

from .models import Customer
from .serializers import (
    AdjustmentInputSerializer,
    CustomerListSerializer,
    CustomerSerializer,
    DebtMovementSerializer,
    RepaymentInputSerializer,
)
from .services import DebtService

_TAG = "CRM"


@extend_schema_view(
    list=extend_schema(summary="Lister les clients", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'un client", tags=[_TAG]),
    create=extend_schema(summary="Créer un client", tags=[_TAG]),
    update=extend_schema(summary="Modifier un client", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier un client (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer un client", tags=[_TAG]),
    debt_history=extend_schema(summary="Historique de dette d'un client", tags=[_TAG]),
    repay=extend_schema(summary="Enregistrer un remboursement", tags=[_TAG]),
    adjust_debt=extend_schema(summary="Ajuster manuellement la dette", tags=[_TAG]),
)
class CustomerViewSet(TenantScopedViewSet):
    queryset = Customer.objects.order_by("name")
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "email", "niu"]
    ordering_fields = ["name", "trust_level", "debt_balance", "created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return CustomerListSerializer
        return CustomerSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        for field in ("type", "trust_level"):
            if field in params:
                qs = qs.filter(**{field: params[field]})
        if "is_express" in params:
            qs = qs.filter(is_express=params["is_express"].lower() in ("true", "1", "yes"))
        if params.get("has_debt") in ("true", "1", "yes"):
            qs = qs.filter(debt_balance__gt=0)
        return qs

    # --- Actions dette -------------------------------------------------------

    @action(detail=True, methods=["get"], url_path="debt")
    def debt_history(self, request, pk=None):
        customer = self.get_object()
        movements = DebtService.history(customer)
        return SuccessResponse(data=DebtMovementSerializer(movements, many=True).data)

    @action(detail=True, methods=["post"], url_path="debt/repay")
    def repay(self, request, pk=None):
        customer = self.get_object()
        serializer = RepaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        try:
            DebtService.repay(
                customer,
                d["amount"],
                reference=d["reference"],
                note=d["note"],
                recorded_by=request.user,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        customer.refresh_from_db(fields=["debt_balance"])
        return SuccessResponse(
            data=CustomerSerializer(customer).data,
            message=SuccessMessage.UPDATED,
        )

    @action(detail=True, methods=["post"], url_path="debt/adjust")
    def adjust_debt(self, request, pk=None):
        customer = self.get_object()
        serializer = AdjustmentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        try:
            DebtService.adjust(
                customer,
                d["amount"],
                note=d["note"],
                recorded_by=request.user,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        customer.refresh_from_db(fields=["debt_balance"])
        return SuccessResponse(
            data=CustomerSerializer(customer).data,
            message=SuccessMessage.UPDATED,
        )
