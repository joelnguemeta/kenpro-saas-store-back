from rest_framework.routers import DefaultRouter

from .views import CreditNoteViewSet, PaymentViewSet, SaleLineViewSet, SaleViewSet

router = DefaultRouter()
router.register("sales", SaleViewSet, basename="sale")
router.register("lines", SaleLineViewSet, basename="saleline")
router.register("payments", PaymentViewSet, basename="payment")
router.register("credit-notes", CreditNoteViewSet, basename="creditnote")

urlpatterns = router.urls
