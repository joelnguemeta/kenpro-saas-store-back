"""
Viewsets du catalogue `inventory`. Tous tenant-scopés (TenantScopedViewSet).
"""
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters
from rest_framework.exceptions import ValidationError

from kenpro_store.viewsets import TenantScopedReadOnlyViewSet, TenantScopedViewSet

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
from .serializers import (
    CategorySerializer,
    LocationSerializer,
    MediaAssetSerializer,
    ProductBarcodeSerializer,
    ProductContentSerializer,
    ProductSerializer,
    ProductVariantSerializer,
    StockLevelSerializer,
    StockMovementSerializer,
    UnitConversionSerializer,
)
from .services import InsufficientStock, StockLedger

_TAG = "Catalogue"


@extend_schema_view(
    list=extend_schema(summary="Lister les catégories", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'une catégorie", tags=[_TAG]),
    create=extend_schema(summary="Créer une catégorie", tags=[_TAG]),
    update=extend_schema(summary="Modifier une catégorie", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier une catégorie (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer une catégorie", tags=[_TAG]),
)
class CategoryViewSet(TenantScopedViewSet):
    queryset = Category.objects.select_related("parent").order_by("name")
    serializer_class = CategorySerializer


@extend_schema_view(
    list=extend_schema(summary="Lister les produits", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'un produit", tags=[_TAG]),
    create=extend_schema(
        summary="Créer un produit",
        description="Le SKU est généré automatiquement (séquentiel par tenant : KP-000001…).",
        tags=[_TAG],
    ),
    update=extend_schema(summary="Modifier un produit", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier un produit (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer un produit", tags=[_TAG]),
)
class ProductViewSet(TenantScopedViewSet):
    queryset = (
        Product.objects.select_related("category")
        .prefetch_related("barcodes", "variants", "media")
        .order_by("sku")
    )
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["sku", "name"]
    ordering_fields = ["sku", "name", "floor_price", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        for field in ("status", "category", "is_published_online"):
            if field in params:
                qs = qs.filter(**{field: params[field]})
        return qs


@extend_schema_view(
    list=extend_schema(summary="Lister les codes-barres", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'un code-barres", tags=[_TAG]),
    create=extend_schema(summary="Créer un code-barres", tags=[_TAG]),
    update=extend_schema(summary="Modifier un code-barres", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier un code-barres (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer un code-barres", tags=[_TAG]),
)
class ProductBarcodeViewSet(TenantScopedViewSet):
    queryset = ProductBarcode.objects.select_related("product").order_by("code")
    serializer_class = ProductBarcodeSerializer


@extend_schema_view(
    list=extend_schema(summary="Lister les variantes", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'une variante", tags=[_TAG]),
    create=extend_schema(summary="Créer une variante", tags=[_TAG]),
    update=extend_schema(summary="Modifier une variante", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier une variante (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer une variante", tags=[_TAG]),
)
class ProductVariantViewSet(TenantScopedViewSet):
    queryset = ProductVariant.objects.select_related("product").order_by("name")
    serializer_class = ProductVariantSerializer


@extend_schema_view(
    list=extend_schema(summary="Lister les médias", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'un média", tags=[_TAG]),
    create=extend_schema(summary="Ajouter un média", tags=[_TAG]),
    update=extend_schema(summary="Modifier un média", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier un média (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer un média", tags=[_TAG]),
)
class MediaAssetViewSet(TenantScopedViewSet):
    queryset = MediaAsset.objects.select_related("product").order_by("order")
    serializer_class = MediaAssetSerializer


@extend_schema_view(
    list=extend_schema(summary="Lister les contenus produit", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'un contenu produit", tags=[_TAG]),
    create=extend_schema(summary="Créer un contenu produit", tags=[_TAG]),
    update=extend_schema(summary="Modifier un contenu produit", tags=[_TAG]),
    partial_update=extend_schema(summary="Modifier un contenu produit (partiel)", tags=[_TAG]),
    destroy=extend_schema(summary="Supprimer un contenu produit", tags=[_TAG]),
)
class ProductContentViewSet(TenantScopedViewSet):
    queryset = ProductContent.objects.select_related("product").order_by("created_at")
    serializer_class = ProductContentSerializer


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------

_STOCK_TAG = "Stock"


@extend_schema_view(
    list=extend_schema(summary="Lister les emplacements", tags=[_STOCK_TAG]),
    retrieve=extend_schema(summary="Détail d'un emplacement", tags=[_STOCK_TAG]),
    create=extend_schema(summary="Créer un emplacement", tags=[_STOCK_TAG]),
    update=extend_schema(summary="Modifier un emplacement", tags=[_STOCK_TAG]),
    partial_update=extend_schema(summary="Modifier un emplacement (partiel)", tags=[_STOCK_TAG]),
    destroy=extend_schema(summary="Supprimer un emplacement", tags=[_STOCK_TAG]),
)
class LocationViewSet(TenantScopedViewSet):
    queryset = Location.objects.order_by("name")
    serializer_class = LocationSerializer


@extend_schema_view(
    list=extend_schema(summary="Lister les conversions d'unité", tags=[_STOCK_TAG]),
    retrieve=extend_schema(summary="Détail d'une conversion d'unité", tags=[_STOCK_TAG]),
    create=extend_schema(summary="Créer une conversion d'unité", tags=[_STOCK_TAG]),
    update=extend_schema(summary="Modifier une conversion d'unité", tags=[_STOCK_TAG]),
    partial_update=extend_schema(summary="Modifier une conversion (partiel)", tags=[_STOCK_TAG]),
    destroy=extend_schema(summary="Supprimer une conversion d'unité", tags=[_STOCK_TAG]),
)
class UnitConversionViewSet(TenantScopedViewSet):
    queryset = UnitConversion.objects.select_related("product").order_by("from_unit")
    serializer_class = UnitConversionSerializer


@extend_schema_view(
    list=extend_schema(summary="Lister les niveaux de stock", tags=[_STOCK_TAG]),
    retrieve=extend_schema(summary="Détail d'un niveau de stock", tags=[_STOCK_TAG]),
)
class StockLevelViewSet(TenantScopedReadOnlyViewSet):
    """Lecture seule : cache recalculé depuis les mouvements."""
    queryset = StockLevel.objects.select_related("product", "variant", "location").order_by(
        "product__sku"
    )
    serializer_class = StockLevelSerializer


@extend_schema_view(
    list=extend_schema(summary="Lister les mouvements de stock", tags=[_STOCK_TAG]),
    retrieve=extend_schema(summary="Détail d'un mouvement", tags=[_STOCK_TAG]),
    create=extend_schema(
        summary="Enregistrer un mouvement de stock",
        description=(
            "Append-only : un mouvement validé est immuable (ni modification ni "
            "suppression). Une sortie qui rendrait le solde négatif est refusée "
            "(survente). Idempotent sur `client_uuid` pour la synchro offline."
        ),
        tags=[_STOCK_TAG],
    ),
)
class StockMovementViewSet(TenantScopedViewSet):
    """Append-only : création + lecture uniquement (ni PUT/PATCH ni DELETE)."""
    queryset = StockMovement.objects.select_related(
        "product", "variant", "location"
    ).order_by("-created_at")
    serializer_class = StockMovementSerializer
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        tenant = self._require_tenant()
        user = self.request.user if self.request.user.is_authenticated else None
        try:
            movement = StockLedger.record_movement(
                tenant=tenant,
                created_by=user,
                **serializer.validated_data,
            )
        except InsufficientStock as exc:
            raise ValidationError({"quantity": str(exc)})
        serializer.instance = movement
