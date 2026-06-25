from rest_framework.routers import DefaultRouter

from .views import DeviceViewSet, RepairTicketViewSet

router = DefaultRouter()
router.register("devices", DeviceViewSet, basename="device")
router.register("tickets", RepairTicketViewSet, basename="repairticket")

urlpatterns = router.urls
