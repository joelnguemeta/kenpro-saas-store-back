from django.contrib import admin

from .models import Payment, Sale, SaleLine


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    readonly_fields = ("floor_price", "catalog_price", "final_price", "line_adjustment", "adjusted_by")


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("reference", "channel", "status", "customer", "seller", "total", "created_at")
    list_filter = ("status", "channel")
    search_fields = ("reference",)
    readonly_fields = ("validated_at",)
    inlines = [SaleLineInline, PaymentInline]


@admin.register(SaleLine)
class SaleLineAdmin(admin.ModelAdmin):
    list_display = ("sale", "product", "quantity", "final_price", "floor_price")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("sale", "method", "amount", "status", "recorded_by")
    list_filter = ("method", "status")
