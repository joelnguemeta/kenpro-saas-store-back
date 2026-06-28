from rest_framework import serializers

from .models import StockAlertConfig


class StockAlertConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockAlertConfig
        fields = [
            "id", "is_enabled", "whatsapp_phone",
            "send_time", "min_alerts_to_send",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
