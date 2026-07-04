"""
Viewsets du catalogue `inventory`. Tous tenant-scopés (TenantScopedViewSet).
"""
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from django.db import models
from django.db.models import Q
from kenpro_store.responses import SuccessResponse
from kenpro_store.viewsets import TenantScopedReadOnlyViewSet, TenantScopedViewSet
from sales.whatsapp import catalog_share_link

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
        from django.db.models import OuterRef, Subquery, IntegerField, Sum
        qs = super().get_queryset()
        params = self.request.query_params
        for field in ("status", "category", "is_published_online"):
            if field in params:
                qs = qs.filter(**{field: params[field]})

        # Annote stock_total (toutes boutiques)
        stock_agg = (
            StockLevel.objects.filter(product=OuterRef("pk"), tenant=OuterRef("tenant"))
            .values("product")
            .annotate(total=Sum("quantity"))
            .values("total")
        )
        qs = qs.annotate(stock_total=Subquery(stock_agg, output_field=IntegerField()))

        # Annote stock_at_location quand ?location= fourni
        location_id = params.get("location")
        if location_id:
            loc_stock = (
                StockLevel.objects.filter(
                    product=OuterRef("pk"),
                    tenant=OuterRef("tenant"),
                    location_id=location_id,
                )
                .values("quantity")[:1]
            )
            qs = qs.annotate(stock_at_location=Subquery(loc_stock, output_field=IntegerField()))

        return qs

    @extend_schema(
        summary="Trouver un produit par code-barres (scan)",
        description=(
            "Recherche exacte : d'abord dans les codes-barres du tenant, "
            "puis en repli sur le SKU. Utilisé par la douchette et le scan caméra. "
            "Passer `?location=<uuid>` pour obtenir aussi `stock_at_location`."
        ),
        parameters=[
            OpenApiParameter(name="code", description="Code-barres ou SKU scanné", required=True, type=str),
            OpenApiParameter(name="location", description="UUID de la boutique", required=False, type=str),
        ],
        tags=[_TAG],
    )
    @action(detail=False, methods=["get"], url_path="scan")
    def scan(self, request):
        from kenpro_store.enums import ErrorCode
        from kenpro_store.responses import ErrorResponse

        code = (request.query_params.get("code") or "").strip()
        if not code:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message="Paramètre `code` requis.",
            )

        qs = self.get_queryset()
        product = qs.filter(barcodes__code=code).first() or qs.filter(sku=code).first()
        if product is None:
            return ErrorResponse(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Aucun produit ne correspond au code « {code} ».",
                status_code=404,
            )
        return SuccessResponse(data=self.get_serializer(product).data)

    @extend_schema(
        summary="Prix suggéré selon le segment tarifaire du client",
        description=(
            "Retourne le prix conseillé pour ce produit en fonction du `pricing_tier` "
            "du client (retail → retail_price, reseller → reseller_price, "
            "wholesale → wholesale_price). "
            "Passer `?customer=<uuid>` pour cibler un client précis, "
            "ou `?tier=retail|reseller|wholesale` directement."
        ),
        parameters=[
            OpenApiParameter(name="customer", description="UUID du client", required=False, type=str),
            OpenApiParameter(name="tier", description="retail | reseller | wholesale", required=False, type=str),
        ],
        tags=["Catalogue"],
    )
    @action(detail=True, methods=["get"], url_path="suggested-price")
    def suggested_price(self, request, pk=None):
        from crm.models import Customer

        product = self.get_object()
        tenant = self._require_tenant()

        tier = request.query_params.get("tier")

        if not tier:
            customer_id = request.query_params.get("customer")
            if customer_id:
                try:
                    customer = Customer.objects.get(id=customer_id, tenant=tenant)
                    tier = customer.pricing_tier
                except Customer.DoesNotExist:
                    tier = Customer.PricingTier.RETAIL
            else:
                tier = Customer.PricingTier.RETAIL

        price_map = {
            Customer.PricingTier.RETAIL: product.retail_price,
            Customer.PricingTier.RESELLER: product.reseller_price,
            Customer.PricingTier.WHOLESALE: product.wholesale_price,
        }
        suggested = price_map.get(tier, product.retail_price)

        return SuccessResponse(data={
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "tier": tier,
            "suggested_price": suggested,
            "floor_price": product.floor_price,
            "prices": {
                "retail": product.retail_price,
                "reseller": product.reseller_price,
                "wholesale": product.wholesale_price,
            },
        })


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

    def get_queryset(self):
        qs = super().get_queryset()
        # Filtres : ?location=<uuid> et ?product=<uuid>
        location = self.request.query_params.get("location")
        if location:
            qs = qs.filter(location_id=location)
        product = self.request.query_params.get("product")
        if product:
            qs = qs.filter(product_id=product)
        return qs


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


class StockAlertView(APIView):
    """
    Liste les produits en rupture ou sous le seuil de réapprovisionnement.
    Retourne uniquement les StockLevel dont reorder_threshold > 0
    et quantity ≤ reorder_threshold, triés par sévérité (critical en premier).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Alertes de stock (rupture et seuil bas)",
        description=(
            "Retourne les niveaux de stock en alerte : "
            "`critical` (quantity ≤ 0) et `low` (0 < quantity ≤ reorder_threshold). "
            "Seuls les emplacements ayant un seuil configuré (reorder_threshold > 0) sont inclus. "
            "Filtrer par boutique avec `?location=<uuid>`."
        ),
        parameters=[
            OpenApiParameter(name="location", description="UUID de la boutique", required=False, type=str),
        ],
        tags=["Stock"],
    )
    def get(self, request):
        from .serializers import StockAlertSerializer

        tenant = getattr(request, "tenant", None)
        if tenant is None:
            from kenpro_store.enums import ErrorCode
            from kenpro_store.responses import ErrorResponse
            return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="Aucun tenant actif.")

        qs = (
            StockLevel.objects.select_related("product", "variant", "location")
            .filter(tenant=tenant, reorder_threshold__gt=0)
            .filter(quantity__lte=models.F("reorder_threshold"))
        )

        location_id = request.query_params.get("location")
        if location_id:
            qs = qs.filter(location=location_id)

        # critical (rupture) avant low (seuil bas)
        from django.db.models import Case, IntegerField, Value, When
        qs = qs.annotate(
            severity=Case(
                When(quantity__lte=0, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("severity", "quantity")

        alerts_data = StockAlertSerializer(qs, many=True).data
        critical = sum(1 for a in alerts_data if a["alert_level"] == "critical")
        return SuccessResponse(data={
            "count": len(alerts_data),
            "critical": critical,
            "low": len(alerts_data) - critical,
            "alerts": alerts_data,
        })


class BarcodeLookupView(APIView):
    """
    Extraction d'infos produit à partir d'un code-barres scanné (création).

    1. Le code correspond à un produit du tenant → on le retourne
       (`source: "catalog"`) pour éviter les doublons.
    2. Sinon, interrogation d'Open Food Facts (base publique mondiale de
       codes-barres) → nom et marque pour pré-remplir le formulaire
       (`source: "external"`).
    3. Rien trouvé → `source: "none"` : l'utilisateur saisit les infos,
       le code sera attaché au produit créé.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Extraire les infos d'un code-barres (catalogue puis base publique)",
        parameters=[
            OpenApiParameter(name="code", description="Code-barres scanné", required=True, type=str),
        ],
        tags=[_TAG],
    )
    def get(self, request):
        from kenpro_store.enums import ErrorCode
        from kenpro_store.responses import ErrorResponse

        code = (request.query_params.get("code") or "").strip()
        if not code:
            return ErrorResponse(error_code=ErrorCode.BAD_REQUEST, message="Paramètre `code` requis.")

        tenant = getattr(request, "tenant", None)

        # 1) Déjà au catalogue de la boutique ?
        if tenant is not None:
            product = Product.objects.filter(tenant=tenant, barcodes__code=code).first()
            if product is not None:
                return SuccessResponse(data={
                    "source": "catalog",
                    "code": code,
                    "product": ProductSerializer(product, context={"request": request}).data,
                })

        # 2) Base publique (Open Food Facts) — best-effort, timeout court
        external = None
        try:
            import json
            from urllib.request import Request, urlopen

            req = Request(
                f"https://world.openfoodfacts.org/api/v2/product/{code}.json"
                "?fields=product_name,brands,quantity",
                headers={"User-Agent": "KenproStore/1.0 (contact@kenpro.cm)"},
            )
            with urlopen(req, timeout=4) as resp:
                payload = json.loads(resp.read())
            if payload.get("status") == 1:
                p = payload.get("product", {})
                name_parts = [p.get("brands", ""), p.get("product_name", ""), p.get("quantity", "")]
                external = {
                    "name": " ".join(s for s in name_parts if s).strip(),
                    "brand": p.get("brands", ""),
                }
        except Exception:
            external = None  # hors-ligne ou code inconnu — pas bloquant

        if external and external["name"]:
            return SuccessResponse(data={"source": "external", "code": code, "suggestion": external})

        return SuccessResponse(data={"source": "none", "code": code})


class CatalogShareView(APIView):
    """
    Génère le lien partageable vers le catalogue en ligne du tenant (F-29).
    Retourne aussi le lien wa.me pré-rempli pour le partage WhatsApp direct.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Lien de partage du catalogue (WhatsApp)",
        tags=["Catalogue"],
    )
    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            raise PermissionDenied("Aucun tenant actif sur la requête.")
        return SuccessResponse(data=catalog_share_link(tenant))
        serializer.instance = movement
