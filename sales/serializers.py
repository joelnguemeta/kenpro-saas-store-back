"""
Sérialiseurs de l'app `sales`.

Snapshot des prix : floor_price et catalog_price sont renseignés par le
client au moment de la création de la ligne (copie depuis le catalogue).
Ils ne sont jamais recalculés a posteriori.
"""
from rest_framework import serializers

from .models import CreditNote, CreditNoteLine, Payment, Sale, SaleLine


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id", "sale", "method", "amount",
            "status", "recorded_by",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at", "updated_at"]


class SaleLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleLine
        fields = [
            "id", "sale", "product", "quantity", "unit",
            "floor_price", "catalog_price", "final_price",
            "line_adjustment", "adjusted_by",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "adjusted_by", "created_at", "updated_at"]


class SaleSerializer(serializers.ModelSerializer):
    """Détail complet d'une vente avec lignes et paiements imbriqués."""
    lines = SaleLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "reference", "channel", "customer", "seller",
            "location", "status",
            "subtotal", "total_discount", "total",
            "validated_at",
            "lines", "payments",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "reference", "seller", "status",
            "subtotal", "total_discount", "total",
            "validated_at", "lines", "payments",
            "created_at", "updated_at",
        ]


class SaleListSerializer(serializers.ModelSerializer):
    """Version allégée pour les listes (sans lignes ni paiements)."""

    class Meta:
        model = Sale
        fields = [
            "id", "reference", "channel", "customer",
            "seller", "location", "status", "total",
            "validated_at", "created_at",
        ]
        read_only_fields = fields


class ValidateSaleSerializer(serializers.Serializer):
    """Payload vide — la validation ne nécessite aucun champ supplémentaire."""
    pass


class CancelSaleSerializer(serializers.Serializer):
    """Payload pour l'annulation d'une vente."""
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class CreditNoteLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="sale_line.product.name", read_only=True)

    class Meta:
        model = CreditNoteLine
        fields = [
            "id", "sale_line", "product_name",
            "quantity", "unit_price", "line_total",
        ]
        read_only_fields = fields


class CreditNoteSerializer(serializers.ModelSerializer):
    lines = CreditNoteLineSerializer(many=True, read_only=True)

    class Meta:
        model = CreditNote
        fields = [
            "id", "sale", "reference", "reason", "note",
            "total", "lines", "created_by", "created_at",
        ]
        read_only_fields = fields


class ReturnLineInputSerializer(serializers.Serializer):
    sale_line = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value="0.001")


class CreateCreditNoteSerializer(serializers.Serializer):
    lines = ReturnLineInputSerializer(many=True, min_length=1)
    reason = serializers.ChoiceField(
        choices=CreditNote.Reason.choices,
        default=CreditNote.Reason.OTHER,
    )
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
