"""
Viewsets de l'app `crm`.
"""
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, status

from kenpro_store.enums import SuccessMessage
from kenpro_store.responses import SuccessResponse
from kenpro_store.viewsets import TenantScopedViewSet

from .models import Customer
from .serializers import CustomerListSerializer, CustomerSerializer

_TAG = "CRM"


@extend_schema_view(
    list=extend_schema(summary="Lister les clients", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'un client", tags=[_TAG]),
    create=extend_schema(summary="Créer un client", tags=[_TAG]),
    update=extend_schema(summary="Modifier un client", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier un client (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer un client", tags=[_TAG]),
)
class CustomerViewSet(TenantScopedViewSet):
    queryset = Customer.objects.order_by("name")
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "email", "niu"]
    ordering_fields = ["name", "trust_level", "created_at"]

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
        # is_express est un BooleanField : convertit la chaîne query param en bool
        if "is_express" in params:
            qs = qs.filter(is_express=params["is_express"].lower() in ("true", "1", "yes"))
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return SuccessResponse(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return SuccessResponse(data=serializer.data)

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
        return SuccessResponse(
            message=SuccessMessage.DELETED,
            status_code=status.HTTP_204_NO_CONTENT,
        )
