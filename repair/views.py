"""
Viewsets de l'app `repair`.

Tous les viewsets héritent de TenantScopedViewSet (filtrage par tenant,
injection du tenant à la création). Les actions métier spécifiques
(transition de statut, assignation) sont exposées comme actions DRF
supplémentaires via @action.
"""
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from kenpro_store.enums import ErrorCode, SuccessMessage
from kenpro_store.responses import ErrorResponse, SuccessResponse
from kenpro_store.viewsets import TenantScopedViewSet

from .models import Device, RepairTicket, StatusHistory
from .serializers import (
    AssignTechnicianSerializer,
    DeviceSerializer,
    RepairTicketListSerializer,
    RepairTicketSerializer,
    StatusHistorySerializer,
    TicketTransitionSerializer,
)

User = get_user_model()

_TAG = "Réparation"

# ---------------------------------------------------------------------------
# Transitions de statut autorisées
# ---------------------------------------------------------------------------

# Graphe de transitions légales : statut courant → statuts suivants possibles
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    RepairTicket.Status.RECEIVED:    [RepairTicket.Status.DIAGNOSED, RepairTicket.Status.CANCELLED, RepairTicket.Status.RETURNED],
    RepairTicket.Status.DIAGNOSED:   [RepairTicket.Status.QUOTE_SENT, RepairTicket.Status.IN_PROGRESS, RepairTicket.Status.RETURNED],
    RepairTicket.Status.QUOTE_SENT:  [RepairTicket.Status.APPROVED, RepairTicket.Status.REJECTED],
    RepairTicket.Status.APPROVED:    [RepairTicket.Status.IN_PROGRESS],
    RepairTicket.Status.IN_PROGRESS: [RepairTicket.Status.TESTED],
    RepairTicket.Status.TESTED:      [RepairTicket.Status.READY, RepairTicket.Status.IN_PROGRESS],
    RepairTicket.Status.READY:       [RepairTicket.Status.DELIVERED],
    # Statuts terminaux — aucune transition sortante
    RepairTicket.Status.DELIVERED:   [],
    RepairTicket.Status.REJECTED:    [RepairTicket.Status.RETURNED],
    RepairTicket.Status.RETURNED:    [],
    RepairTicket.Status.CANCELLED:   [],
}


# ---------------------------------------------------------------------------
# Appareil
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="Lister les appareils", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'un appareil", tags=[_TAG]),
    create=extend_schema(summary="Enregistrer un appareil", tags=[_TAG]),
    update=extend_schema(summary="Modifier un appareil", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier un appareil (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer un appareil", tags=[_TAG]),
)
class DeviceViewSet(TenantScopedViewSet):
    queryset = Device.objects.select_related("customer").order_by("brand", "model")
    serializer_class = DeviceSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["brand", "model", "imei_serial", "customer__name"]
    ordering_fields = ["brand", "model", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        # Filtrage optionnel par type d'appareil
        device_type = self.request.query_params.get("type")
        if device_type:
            qs = qs.filter(type=device_type)
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
        instance = self.get_object()
        serializer = self.get_serializer(instance)
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
        instance = self.get_object()
        self.perform_destroy(instance)
        return SuccessResponse(message=SuccessMessage.DELETED, status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Ticket de réparation
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="Lister les tickets de réparation", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'un ticket (avec historique)", tags=[_TAG]),
    create=extend_schema(summary="Ouvrir un ticket de réparation", tags=[_TAG]),
    update=extend_schema(summary="Modifier un ticket", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier un ticket (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer un ticket", tags=[_TAG]),
)
class RepairTicketViewSet(TenantScopedViewSet):
    queryset = RepairTicket.objects.none()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["device__imei_serial", "device__brand", "customer__name"]
    ordering_fields = ["intake_at", "status", "created_at"]

    def get_queryset(self):
        qs = RepairTicket.objects.select_related(
            "device", "customer", "technician", "location"
        ).prefetch_related("history")

        # Filtrage par tenant
        tenant = self._require_tenant()
        qs = qs.filter(tenant=tenant)

        # Filtres optionnels via query params
        params = self.request.query_params
        for field in ("status", "technician", "location"):
            if field in params:
                qs = qs.filter(**{field: params[field]})

        return qs.order_by("-intake_at")

    def get_serializer_class(self):
        # Liste allégée, détail complet avec historique
        if self.action == "list":
            return RepairTicketListSerializer
        return RepairTicketSerializer

    # --- CRUD standard avec SuccessResponse ---

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return SuccessResponse(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return SuccessResponse(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Recharge avec l'historique pour la réponse
        full = RepairTicketSerializer(serializer.instance, context=self.get_serializer_context())
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
        instance = self.get_object()
        self.perform_destroy(instance)
        return SuccessResponse(message=SuccessMessage.DELETED, status_code=status.HTTP_204_NO_CONTENT)

    # --- Actions métier ---

    @extend_schema(
        summary="Changer le statut d'un ticket",
        description=(
            "Effectue une transition de statut selon le graphe autorisé. "
            "Crée automatiquement une entrée dans l'historique (append-only)."
        ),
        request=TicketTransitionSerializer,
        tags=[_TAG],
    )
    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        ticket = self.get_object()
        serializer = TicketTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        to_status = serializer.validated_data["to_status"]
        note = serializer.validated_data.get("note", "")

        # Vérifie que la transition est légale
        allowed = ALLOWED_TRANSITIONS.get(ticket.status, [])
        if to_status not in allowed:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message=(
                    f"Transition « {ticket.status} → {to_status} » interdite. "
                    f"Transitions autorisées : {allowed or 'aucune (statut terminal)'}."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        from_status = ticket.status
        ticket.status = to_status
        ticket.save()

        # Écriture append-only dans l'historique
        StatusHistory.objects.create(
            tenant=ticket.tenant,
            ticket=ticket,
            from_status=from_status,
            to_status=to_status,
            changed_by=request.user,
            note=note,
        )

        full = RepairTicketSerializer(ticket, context=self.get_serializer_context())
        return SuccessResponse(
            data=full.data,
            message=f"Ticket passé en « {ticket.get_status_display()} ».",
        )

    @extend_schema(
        summary="Assigner un technicien",
        description="Assigne un technicien au ticket (permission repair:assign requise).",
        request=AssignTechnicianSerializer,
        tags=[_TAG],
    )
    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request, pk=None):
        ticket = self.get_object()
        serializer = AssignTechnicianSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant = self._require_tenant()
        technician = get_object_or_404(
            User,
            pk=serializer.validated_data["technician_id"],
            memberships__tenant=tenant,
            memberships__is_active=True,
        )
        ticket.technician = technician
        ticket.save()

        full = RepairTicketSerializer(ticket, context=self.get_serializer_context())
        return SuccessResponse(
            data=full.data,
            message=f"Technicien « {technician} » assigné.",
        )

    @extend_schema(
        summary="Historique des statuts d'un ticket",
        tags=[_TAG],
    )
    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        ticket = self.get_object()
        entries = ticket.history.select_related("changed_by").order_by("created_at")
        serializer = StatusHistorySerializer(entries, many=True)
        return SuccessResponse(data=serializer.data)
