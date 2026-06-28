from django.contrib import admin

from .models import MobileMoneyTransaction


@admin.register(MobileMoneyTransaction)
class MobileMoneyTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "reference", "operator", "payer_phone", "amount", "currency",
        "status", "sale", "status_updated_at", "created_at",
    )
    list_filter = ("operator", "status")
    search_fields = ("reference", "external_id", "payer_phone", "sale__reference")
    readonly_fields = (
        "external_id", "provider_response", "payment",
        "status_updated_at", "created_at", "updated_at",
    )
