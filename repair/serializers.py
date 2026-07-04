"""
Sérialiseurs de l'app `repair`.

Conventions :
  - Le champ `tenant` n'est jamais accepté en entrée (injecté par le viewset).
  - Les FK internes sont validées pour appartenir au même tenant.
  - `StatusHistory` est en lecture seule depuis l'API (créé par le service
    de transition, jamais directement par le client).
"""
from rest_framework import serializers

from .models import Device, RepairTicket, StatusHistory


# ---------------------------------------------------------------------------
# Appareil
# ---------------------------------------------------------------------------

class DeviceSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)

    class Meta:
        model = Device
        fields = [
            "id", "customer", "customer_name", "type", "brand", "model",
            "imei_serial", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# Ticket
# ---------------------------------------------------------------------------

class StatusHistorySerializer(serializers.ModelSerializer):
    """Lecture seule — les transitions passent par l'action `transition`."""

    class Meta:
        model = StatusHistory
        fields = [
            "id", "from_status", "to_status", "changed_by",
            "note", "created_at",
        ]
        read_only_fields = fields


class RepairTicketSerializer(serializers.ModelSerializer):
    """
    Sérialiseur de base : création et modification d'un ticket.
    L'historique des statuts est accessible en lecture via `history`.
    """
    # Historique imbriqué en lecture seule
    history = StatusHistorySerializer(many=True, read_only=True)
    # Infos d'affichage (évitent des requêtes supplémentaires côté frontend)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    device_info = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    # Transitions légales depuis le statut courant — pilote les boutons de l'UI
    allowed_transitions = serializers.SerializerMethodField()

    def get_device_info(self, obj):
        d = obj.device
        return {
            "id": str(d.id),
            "type": d.type,
            "brand": d.brand,
            "model": d.model,
            "imei_serial": d.imei_serial,
        }

    def get_allowed_transitions(self, obj):
        from .views import ALLOWED_TRANSITIONS
        return [
            {"value": s, "label": RepairTicket.Status(s).label}
            for s in ALLOWED_TRANSITIONS.get(obj.status, [])
        ]

    class Meta:
        model = RepairTicket
        fields = [
            "id", "device", "device_info", "customer", "customer_name",
            "declared_issue", "status", "status_display",
            "allowed_transitions",
            "technician", "location", "intake_at",
            "history",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "history", "created_at", "updated_at"]


class RepairTicketListSerializer(serializers.ModelSerializer):
    """
    Version allégée pour les listes (sans historique imbriqué).
    Évite le surcoût des N+1 sur les listes longues.
    """
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    device_info = serializers.SerializerMethodField()

    def get_device_info(self, obj):
        d = obj.device
        return {
            "id": str(d.id),
            "type": d.type,
            "brand": d.brand,
            "model": d.model,
            "imei_serial": d.imei_serial,
        }

    class Meta:
        model = RepairTicket
        fields = [
            "id", "device", "device_info", "customer", "customer_name",
            "status", "status_display",
            "technician", "location", "intake_at",
            "created_at",
        ]
        read_only_fields = fields


class TicketTransitionSerializer(serializers.Serializer):
    """
    Payload pour l'action `transition` : changement de statut + note optionnelle.
    La validation du cycle de vie (quelles transitions sont légales) est faite
    dans le viewset / service, pas ici.
    """
    to_status = serializers.ChoiceField(choices=RepairTicket.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class AssignTechnicianSerializer(serializers.Serializer):
    """Payload pour l'action `assign` : désignation d'un technicien."""
    technician_id = serializers.UUIDField()
