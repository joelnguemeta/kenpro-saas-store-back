"""
URL configuration for kenpro_store project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenRefreshView

from .views import DashboardView, FiscalReportView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/accounts/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/v1/dashboard/", DashboardView.as_view(), name="dashboard"),
    path("api/v1/fiscal/report/", FiscalReportView.as_view(), name="fiscal-report"),
    path("api/v1/accounts/", include("accounts.urls")),
    path("api/v1/inventory/", include("inventory.urls")),
    path("api/v1/crm/", include("crm.urls")),
    path("api/v1/sales/", include("sales.urls")),
    path("api/v1/supplier/", include("supplier.urls")),
    path("api/v1/repair/", include("repair.urls")),
    path("api/v1/mobilemoney/", include("mobilemoney.urls")),
    path("api/v1/notifications/", include("notifications.urls")),
    # Schéma OpenAPI brut (JSON/YAML)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # ReDoc (alternative plus lisible)
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
