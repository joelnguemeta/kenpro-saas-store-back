"""
Sérialiseurs de l'app `crm`.
"""
from rest_framework import serializers

from .models import Customer, DebtMovement


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone", "email",
            "type", "niu", "trust_level",
            "is_express", "notes", "debt_balance",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "debt_balance", "created_at", "updated_at"]


class CustomerListSerializer(serializers.ModelSerializer):
    """Version allégée pour les listes (sans notes)."""

    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone", "email",
            "type", "trust_level", "is_express",
            "debt_balance", "created_at",
        ]
        read_only_fields = fields


class DebtMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtMovement
        fields = [
            "id", "type", "amount", "reference",
            "note", "recorded_by", "created_at",
        ]
        read_only_fields = fields


class RepaymentInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value="0.01")
    reference = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class AdjustmentInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    note = serializers.CharField(max_length=500)
