"""
Viewset Mobile Money — F-17, F-18, F-19.
"""
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from kenpro_store.enums import SuccessMessage
from kenpro_store.responses import ErrorResponse, SuccessResponse
from kenpro_store.enums import ErrorCode
from kenpro_store.viewsets import TenantScopedReadOnlyViewSet

from sales.models import Sale

from .models import MobileMoneyTransaction
from .serializers import InitiatePaymentSerializer, MobileMoneyTransactionSerializer
from .services import MobileMoneyService

_TAG = "Mobile Money"


@extend_schema_view(
    list=extend_schema(summary="Lister les transactions Mobile Money", tags=[_TAG]),
    retrieve=extend_schema(summary="Détail d'une transaction", tags=[_TAG]),
)
class MobileMoneyTransactionViewSet(TenantScopedReadOnlyViewSet):
    queryset = MobileMoneyTransaction.objects.select_related("sale", "payment")
    serializer_class = MobileMoneyTransactionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if sale_id := params.get("sale"):
            qs = qs.filter(sale=sale_id)
        if status := params.get("status"):
            qs = qs.filter(status=status)
        if operator := params.get("operator"):
            qs = qs.filter(operator=operator)
        return qs.order_by("-created_at")

    @extend_schema(
        summary="Initier un paiement Mobile Money",
        description=(
            "Envoie la demande de débit à l'opérateur (MTN MoMo ou Orange Money). "
            "Retourne immédiatement avec status='pending' — le client doit confirmer "
            "sur son téléphone. Utiliser l'action /check pour rafraîchir le statut."
        ),
        request=InitiatePaymentSerializer,
        tags=[_TAG],
    )
    @action(detail=False, methods=["post"], url_path="initiate")
    def initiate(self, request):
        tenant = self._require_tenant()
        s = InitiatePaymentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        try:
            sale = Sale.objects.get(pk=d["sale"], tenant=tenant)
        except Sale.DoesNotExist:
            raise NotFound("Vente introuvable.")

        if sale.status != Sale.Status.VALIDATED:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message="La vente doit être validée avant d'initier un paiement Mobile Money.",
            )

        try:
            momo_tx = MobileMoneyService.initiate(
                tenant=tenant,
                sale=sale,
                operator=d["operator"],
                payer_phone=d["payer_phone"],
                amount=d["amount"],
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        return SuccessResponse(
            data=MobileMoneyTransactionSerializer(momo_tx).data,
            message="Demande de paiement envoyée. En attente de confirmation du client.",
            status_code=202,
        )

    @extend_schema(
        summary="Vérifier le statut d'une transaction",
        description="Interroge l'opérateur et met à jour le statut en base (F-19).",
        tags=[_TAG],
    )
    @action(detail=True, methods=["post"], url_path="check")
    def check(self, request, pk=None):
        momo_tx = self.get_object()
        momo_tx = MobileMoneyService.check_and_update(
            momo_tx, recorded_by=request.user
        )
        return SuccessResponse(data=MobileMoneyTransactionSerializer(momo_tx).data)
