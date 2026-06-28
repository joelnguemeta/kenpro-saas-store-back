"""
API de configuration des alertes stock WhatsApp par tenant.

GET  /api/v1/notifications/stock-alert-config/  → lit la config du tenant
PUT  /api/v1/notifications/stock-alert-config/  → crée ou met à jour
POST /api/v1/notifications/stock-alert-config/test/  → envoie un test immédiat
"""
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from kenpro_store.enums import ErrorCode
from kenpro_store.responses import ErrorResponse, SuccessResponse

from .models import StockAlertConfig
from .serializers import StockAlertConfigSerializer


class StockAlertConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_tenant(self, request):
        return getattr(request, "tenant", None)

    @extend_schema(
        summary="Lire la configuration d'alerte stock WhatsApp",
        tags=["Notifications"],
    )
    def get(self, request):
        tenant = self._get_tenant(request)
        if not tenant:
            return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="Aucun tenant actif.")

        config = StockAlertConfig.objects.filter(tenant=tenant).first()
        if not config:
            return SuccessResponse(data=None)
        return SuccessResponse(data=StockAlertConfigSerializer(config).data)

    @extend_schema(
        summary="Créer ou mettre à jour la configuration d'alerte stock",
        request=StockAlertConfigSerializer,
        tags=["Notifications"],
    )
    def put(self, request):
        tenant = self._get_tenant(request)
        if not tenant:
            return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="Aucun tenant actif.")

        config, _ = StockAlertConfig.objects.get_or_create(tenant=tenant)
        serializer = StockAlertConfigSerializer(config, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=tenant)
        return SuccessResponse(data=serializer.data)

    @extend_schema(
        summary="Mettre à jour partiellement la configuration",
        request=StockAlertConfigSerializer,
        tags=["Notifications"],
    )
    def patch(self, request):
        tenant = self._get_tenant(request)
        if not tenant:
            return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="Aucun tenant actif.")

        config, _ = StockAlertConfig.objects.get_or_create(tenant=tenant)
        serializer = StockAlertConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=tenant)
        return SuccessResponse(data=serializer.data)


class StockAlertTestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Envoyer une alerte stock de test immédiatement",
        description="Déclenche la tâche d'alerte pour ce tenant sans attendre l'heure planifiée.",
        tags=["Notifications"],
    )
    def post(self, request):
        tenant = self._get_tenant(request)
        if not tenant:
            return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="Aucun tenant actif.")

        config = StockAlertConfig.objects.filter(tenant=tenant, is_enabled=True).first()
        if not config:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message="Aucune configuration active. Configurez d'abord votre numéro WhatsApp.",
            )

        from .tasks import send_stock_alert_for_tenant
        send_stock_alert_for_tenant.delay(str(tenant.id))
        return SuccessResponse(data={"queued": True}, message="Alerte envoyée en file d'attente.")

    def _get_tenant(self, request):
        return getattr(request, "tenant", None)
