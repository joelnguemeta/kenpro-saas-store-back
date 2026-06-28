"""
Sérialiseurs du catalogue `inventory`.

Le `tenant` n'est jamais accepté en entrée : il est injecté par le viewset
(TenantScopedViewSet) à partir du tenant actif. Les FKs internes sont validées
pour garantir qu'elles appartiennent au même tenant — aucune fuite entre
boutiques via un identifiant deviné.
"""
from rest_framework import serializers

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


class TenantScopedSerializer(serializers.ModelSerializer):
    """
    Fournit un validateur réutilisable garantissant qu'une cible de FK
    appartient au tenant de la requête courante.
    """

    def _check_same_tenant(self, value, label):
        if value is None:
            return value
        tenant = getattr(self.context.get("request"), "tenant", None)
        if tenant is not None and value.tenant_id != tenant.id:
            raise serializers.ValidationError(f"{label} introuvable pour ce tenant.")
        return value


class CategorySerializer(TenantScopedSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "name_fr", "name_en", "parent", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_parent(self, value):
        return self._check_same_tenant(value, "Catégorie parente")


class ProductSerializer(TenantScopedSerializer):
    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "name_fr", "name_en", "category", "base_unit",
            "cost", "floor_price", "retail_price",
            "reseller_price", "wholesale_price", "public_price",
            "status", "is_published_online",
            "created_at", "updated_at",
        ]
        # sku auto-généré par tenant (cf. Product.save).
        read_only_fields = ["id", "sku", "created_at", "updated_at"]

    def validate_category(self, value):
        return self._check_same_tenant(value, "Catégorie")


class ProductBarcodeSerializer(TenantScopedSerializer):
    class Meta:
        model = ProductBarcode
        fields = ["id", "product", "code", "is_primary", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_product(self, value):
        return self._check_same_tenant(value, "Produit")


class ProductVariantSerializer(TenantScopedSerializer):
    effective_floor_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = ProductVariant
        fields = [
            "id", "product", "name", "name_fr", "name_en", "attributes", "sku",
            "floor_price", "effective_floor_price",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "effective_floor_price", "created_at", "updated_at"]

    def validate_product(self, value):
        return self._check_same_tenant(value, "Produit")


class MediaAssetSerializer(TenantScopedSerializer):
    class Meta:
        model = MediaAsset
        fields = ["id", "product", "type", "url", "order", "is_primary",
                  "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_product(self, value):
        return self._check_same_tenant(value, "Produit")


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------

class LocationSerializer(TenantScopedSerializer):
    class Meta:
        model = Location
        fields = ["id", "name", "name_fr", "name_en", "type", "is_default", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class UnitConversionSerializer(TenantScopedSerializer):
    class Meta:
        model = UnitConversion
        fields = ["id", "product", "from_unit", "to_unit", "factor",
                  "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_product(self, value):
        return self._check_same_tenant(value, "Produit")


class StockLevelSerializer(serializers.ModelSerializer):
    """Lecture seule : cache recalculé depuis les mouvements."""
    class Meta:
        model = StockLevel
        fields = ["id", "product", "variant", "location", "quantity",
                  "reorder_threshold", "updated_at"]
        read_only_fields = fields


class StockAlertSerializer(serializers.ModelSerializer):
    """Niveau de stock en alerte (quantity ≤ reorder_threshold)."""
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    alert_level = serializers.SerializerMethodField()

    class Meta:
        model = StockLevel
        fields = [
            "id", "product", "product_sku", "product_name",
            "variant", "location", "location_name",
            "quantity", "reorder_threshold", "alert_level",
            "updated_at",
        ]
        read_only_fields = fields

    def get_alert_level(self, obj) -> str:
        if obj.quantity <= 0:
            return "critical"
        return "low"


class StockMovementSerializer(TenantScopedSerializer):
    """
    Append-only : création uniquement. Le mouvement est enregistré via le
    stock ledger (cf. StockMovementViewSet.perform_create).
    """
    signed_quantity = serializers.DecimalField(
        max_digits=16, decimal_places=3, read_only=True
    )

    class Meta:
        model = StockMovement
        fields = [
            "id", "product", "variant", "location", "type", "quantity",
            "signed_quantity", "unit", "reason", "reference", "client_uuid",
            "created_by", "created_at",
        ]
        read_only_fields = ["id", "signed_quantity", "created_by", "created_at"]

    def validate_product(self, value):
        return self._check_same_tenant(value, "Produit")

    def validate_location(self, value):
        return self._check_same_tenant(value, "Emplacement")

    def validate_variant(self, value):
        return self._check_same_tenant(value, "Variante")


class ProductContentSerializer(TenantScopedSerializer):
    class Meta:
        model = ProductContent
        fields = [
            "id", "product",
            "long_description", "long_description_fr", "long_description_en",
            "seo_title", "seo_title_fr", "seo_title_en",
            "seo_description", "seo_description_fr", "seo_description_en",
            "online_status", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_product(self, value):
        return self._check_same_tenant(value, "Produit")
