from rest_framework.routers import DefaultRouter

from .views import MobileMoneyTransactionViewSet

router = DefaultRouter()
router.register("transactions", MobileMoneyTransactionViewSet, basename="momo-transaction")

urlpatterns = router.urls
