from django.contrib import admin

from .models import (
    Category,
    Location,
    MediaAsset,
    Product,
    ProductBarcode,
    ProductContent,
    ProductVariant,
    StockLevel,
    StockMovement,
    UnitConversion,
)


class ProductBarcodeInline(admin.TabularInline):
    model = ProductBarcode
    extra = 0


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


class MediaAssetInline(admin.TabularInline):
    model = MediaAsset
    extra = 0


class ProductContentInline(admin.StackedInline):
    model = ProductContent
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "category", "floor_price", "status", "is_published_online")
    list_filter = ("status", "is_published_online", "category")
    search_fields = ("sku", "name")
    readonly_fields = ("sku",)
    inlines = [ProductBarcodeInline, ProductVariantInline, MediaAssetInline, ProductContentInline]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "tenant")
    search_fields = ("name",)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "is_default", "tenant")
    list_filter = ("type", "is_default")
    search_fields = ("name",)


@admin.register(StockLevel)
class StockLevelAdmin(admin.ModelAdmin):
    list_display = ("product", "variant", "location", "quantity", "reorder_threshold")
    list_filter = ("location",)
    search_fields = ("product__sku", "product__name")
    # Cache recalculable — lecture seule dans l'admin.
    readonly_fields = ("quantity",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "type", "product", "location", "signed_quantity", "reference")
    list_filter = ("type", "location")
    search_fields = ("product__sku", "product__name", "reference")
    # Append-only : aucune modification ni suppression depuis l'admin.
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UnitConversion)
class UnitConversionAdmin(admin.ModelAdmin):
    list_display = ("product", "from_unit", "to_unit", "factor")
    search_fields = ("product__sku", "product__name")
