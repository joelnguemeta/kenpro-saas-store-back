from django.contrib import admin

from .models import CreditEntry, CreditPayment, CreditStatement, Supplier, SupplierLink


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email")
    search_fields = ("name", "phone", "email")


@admin.register(SupplierLink)
class SupplierLinkAdmin(admin.ModelAdmin):
    list_display = ("supplier", "tenant", "credit_ceiling")
    list_filter = ("tenant",)
    search_fields = ("supplier__name",)


@admin.register(CreditStatement)
class CreditStatementAdmin(admin.ModelAdmin):
    list_display = ("supplier_link", "balance", "status", "created_at")
    list_filter = ("status",)


@admin.register(CreditEntry)
class CreditEntryAdmin(admin.ModelAdmin):
    list_display = ("statement", "type", "amount", "created_by", "created_at")
    list_filter = ("type",)

    # Écriture append-only : aucune modification possible depuis l'admin
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CreditPayment)
class CreditPaymentAdmin(admin.ModelAdmin):
    list_display = ("statement", "amount", "method", "status", "recorded_by", "created_at")
    list_filter = ("method", "status")
