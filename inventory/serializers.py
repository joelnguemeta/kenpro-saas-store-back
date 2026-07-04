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
    # Champs lisibles aliasés pour le frontend
    price_retail = serializers.DecimalField(source="retail_price", max_digits=14, decimal_places=2, read_only=True)
    price_floor = serializers.DecimalField(source="floor_price", max_digits=14, decimal_places=2, read_only=True)
    price_reseller = serializers.DecimalField(source="reseller_price", max_digits=14, decimal_places=2, read_only=True)
    price_wholesale = serializers.DecimalField(source="wholesale_price", max_digits=14, decimal_places=2, read_only=True)
    price_public = serializers.DecimalField(source="public_price", max_digits=14, decimal_places=2, read_only=True)
    is_active = serializers.SerializerMethodField()
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    # stock_total / stock_at_location sont annotés par le ViewSet
    stock_total = serializers.IntegerField(read_only=True, default=0)
    stock_at_location = serializers.IntegerField(read_only=True, default=None)
    thumbnail = serializers.SerializerMethodField()
    primary_barcode = serializers.SerializerMethodField()
    # Écriture : code scanné à la création → crée le ProductBarcode principal
    barcode = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=64)

    def get_primary_barcode(self, obj):
        primary = next((b for b in obj.barcodes.all() if b.is_primary), None)
        if primary is None:
            primary = next(iter(obj.barcodes.all()), None)
        return primary.code if primary else None

    def get_is_active(self, obj):
        return obj.status == Product.ACTIVE

    def get_thumbnail(self, obj):
        media = next((m for m in obj.media.all() if m.is_primary), None)
        if media is None and obj.media.exists():
            media = obj.media.first()
        return media.url if media else None

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "name_fr", "name_en",
            "category", "category_name",
            "base_unit",
            "cost", "floor_price", "retail_price",
            "reseller_price", "wholesale_price", "public_price",
            # aliases frontend
            "price_floor", "price_retail", "price_reseller", "price_wholesale", "price_public",
            "status", "is_active", "is_published_online",
            "stock_total", "stock_at_location",
            "thumbnail", "primary_barcode", "barcode",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "sku", "created_at", "updated_at"]

    def validate_category(self, value):
        return self._check_same_tenant(value, "Catégorie")

    def validate_barcode(self, value):
        """Refuse un code déjà utilisé par un autre produit du tenant."""
        value = (value or "").strip()
        if not value:
            return value
        tenant = getattr(self.context.get("request"), "tenant", None)
        qs = ProductBarcode.objects.filter(tenant=tenant, code=value)
        if self.instance is not None:
            qs = qs.exclude(product=self.instance)
        if qs.exists():
            raise serializers.ValidationError("Ce code-barres est déjà associé à un autre produit.")
        return value

    def _attach_barcode(self, product, code):
        if not code:
            return
        ProductBarcode.objects.get_or_create(
            tenant=product.tenant,
            code=code,
            defaults={"product": product, "is_primary": True},
        )

    def create(self, validated_data):
        code = validated_data.pop("barcode", "")
        product = super().create(validated_data)
        self._attach_barcode(product, code)
        return product

    def update(self, instance, validated_data):
        code = validated_data.pop("barcode", None)
        product = super().update(instance, validated_data)
        if code is not None:
            self._attach_barcode(product, code.strip())
        return product


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
        fields = [
            "id", "name", "name_fr", "name_en", "type", "is_default",
            # Surcharges de la config tenant (vide = hérite de TenantSettings)
            "contact_phone", "whatsapp_number", "contact_email",
            "address", "receipt_footer", "email_signature",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def _ensure_single_default(self, instance):
        """Un seul emplacement par défaut par tenant."""
        if instance.is_default:
            Location.objects.filter(tenant=instance.tenant, is_default=True).exclude(
                pk=instance.pk
            ).update(is_default=False)

    def create(self, validated_data):
        instance = super().create(validated_data)
        self._ensure_single_default(instance)
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._ensure_single_default(instance)
        return instance


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
