from rest_framework import serializers

from .models import MobileMoneyTransaction


class MobileMoneyTransactionSerializer(serializers.ModelSerializer):
    operator_display = serializers.CharField(source="get_operator_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = MobileMoneyTransaction
        fields = [
            "id", "sale", "operator", "operator_display",
            "payer_phone", "amount", "currency",
            "status", "status_display",
            "reference", "external_id",
            "failure_reason",
            "payment",
            "status_updated_at", "created_at",
        ]
        read_only_fields = fields


class InitiatePaymentSerializer(serializers.Serializer):
    sale = serializers.UUIDField()
    operator = serializers.ChoiceField(choices=MobileMoneyTransaction.Operator.choices)
    payer_phone = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value="1")
