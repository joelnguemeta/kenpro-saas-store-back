"""
Sérialiseurs de l'app `supplier`.

CreditEntry est append-only : aucun serializer d'update n'est fourni.
CreditPayment suit le même principe (pas de PATCH/PUT exposé).
"""
from rest_framework import serializers

from .models import (
    CreditEntry,
    CreditPayment,
    CreditStatement,
    Supplier,
    SupplierLink,
)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "phone", "email", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class SupplierLinkSerializer(serializers.ModelSerializer):
    # Lecture : fournisseur imbriqué ; écriture : `supplier` = UUID
    supplier = SupplierSerializer(read_only=True)
    supplier_id = serializers.PrimaryKeyRelatedField(
        source="supplier", queryset=Supplier.objects.all(), write_only=True
    )
    current_balance = serializers.SerializerMethodField()

    def get_current_balance(self, obj):
        stmt = obj.statements.filter(status=CreditStatement.Status.OPEN).first()
        return str(stmt.balance) if stmt else "0.00"

    class Meta:
        model = SupplierLink
        fields = [
            "id", "supplier", "supplier_id", "credit_ceiling",
            "current_balance",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "current_balance", "created_at", "updated_at"]


class CreditEntrySerializer(serializers.ModelSerializer):
    """Append-only : pas de champ update."""

    class Meta:
        model = CreditEntry
        fields = [
            "id", "statement", "type", "amount",
            "created_by", "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]


class CreditPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditPayment
        fields = [
            "id", "statement", "amount", "method",
            "status", "recorded_by",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at", "updated_at"]


class CreditStatementSerializer(serializers.ModelSerializer):
    """Détail d'un relevé avec ses écritures et paiements imbriqués."""
    entries = CreditEntrySerializer(many=True, read_only=True)
    payments = CreditPaymentSerializer(many=True, read_only=True)

    class Meta:
        model = CreditStatement
        fields = [
            "id", "supplier_link", "balance", "status",
            "entries", "payments",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "balance", "entries", "payments", "created_at", "updated_at"]


class CreditStatementListSerializer(serializers.ModelSerializer):
    """Version allégée pour les listes."""

    class Meta:
        model = CreditStatement
        fields = [
            "id", "supplier_link", "balance", "status", "created_at",
        ]
        read_only_fields = fields


class ConfirmPaymentSerializer(serializers.Serializer):
    """Payload vide — la confirmation ne nécessite aucun champ."""
    pass
