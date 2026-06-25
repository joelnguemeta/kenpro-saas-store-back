from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    LocationViewSet,
    MediaAssetViewSet,
    ProductBarcodeViewSet,
    ProductContentViewSet,
    ProductVariantViewSet,
    ProductViewSet,
    StockLevelViewSet,
    StockMovementViewSet,
    UnitConversionViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("barcodes", ProductBarcodeViewSet, basename="barcode")
router.register("variants", ProductVariantViewSet, basename="variant")
router.register("media", MediaAssetViewSet, basename="media")
router.register("product-content", ProductContentViewSet, basename="productcontent")
router.register("locations", LocationViewSet, basename="location")
router.register("unit-conversions", UnitConversionViewSet, basename="unitconversion")
router.register("stock-levels", StockLevelViewSet, basename="stocklevel")
router.register("stock-movements", StockMovementViewSet, basename="stockmovement")

urlpatterns = router.urls
