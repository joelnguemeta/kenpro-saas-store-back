"""
Sérialiseurs de l'app `crm`.
"""
from rest_framework import serializers

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone", "email",
            "type", "niu", "trust_level",
            "is_express", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CustomerListSerializer(serializers.ModelSerializer):
    """Version allégée pour les listes (sans notes)."""

    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone", "email",
            "type", "trust_level", "is_express",
            "created_at",
        ]
        read_only_fields = fields
