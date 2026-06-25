from rest_framework.routers import DefaultRouter

from .views import (
    CreditEntryViewSet,
    CreditPaymentViewSet,
    CreditStatementViewSet,
    SupplierLinkViewSet,
    SupplierViewSet,
)

router = DefaultRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("links", SupplierLinkViewSet, basename="supplierlink")
router.register("statements", CreditStatementViewSet, basename="creditstatement")
router.register("entries", CreditEntryViewSet, basename="creditentry")
router.register("credit-payments", CreditPaymentViewSet, basename="creditpayment")

urlpatterns = router.urls
