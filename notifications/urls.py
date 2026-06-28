from django.urls import path

from .views import StockAlertConfigView, StockAlertTestView

urlpatterns = [
    path("stock-alert-config/", StockAlertConfigView.as_view(), name="stock-alert-config"),
    path("stock-alert-config/test/", StockAlertTestView.as_view(), name="stock-alert-test"),
]
