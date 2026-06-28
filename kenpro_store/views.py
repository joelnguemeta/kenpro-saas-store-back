"""
Vues transversales de la plateforme (dashboard, health, etc.).
"""
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from inventory.models import Location

from .dashboard import build_dashboard
from .fiscal import build_fiscal_report
from .responses import ErrorResponse, SuccessResponse
from .enums import ErrorCode


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Tableau de bord (global ou par boutique)",
        description=(
            "Retourne le CA (jour / semaine / mois), la marge brute, "
            "le solde de caisse du jour, le total des dettes clients "
            "et le top 5 des produits les plus vendus ce mois. "
            "Passer `?location=<uuid>` pour filtrer sur une boutique précise."
        ),
        parameters=[
            OpenApiParameter(
                name="location",
                description="UUID d'un emplacement (boutique) pour filtrer les stats.",
                required=False,
                type=str,
            )
        ],
        tags=["Tableau de bord"],
    )
    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return ErrorResponse(
                error_code=ErrorCode.FORBIDDEN,
                message="Aucun tenant actif sur la requête.",
            )

        location = None
        location_id = request.query_params.get("location")
        if location_id:
            try:
                location = Location.objects.get(id=location_id, tenant=tenant)
            except (Location.DoesNotExist, Exception):
                return ErrorResponse(
                    error_code=ErrorCode.NOT_FOUND,
                    message="Boutique introuvable ou n'appartient pas à ce tenant.",
                )

        data = build_dashboard(tenant, location=location)
        return SuccessResponse(data=data)


class FiscalReportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Rapport d'optimisation fiscale",
        description=(
            "Calcule les postes légalement déductibles sur la période : "
            "CA brut, avoirs, coût des marchandises vendues (CMV), pertes de stock déclarées. "
            "Tous les chiffres correspondent aux transactions réelles enregistrées. "
            "Paramètres requis : `date_from` et `date_to` (format YYYY-MM-DD)."
        ),
        parameters=[
            OpenApiParameter(name="date_from", description="Début de période (YYYY-MM-DD)", required=True, type=str),
            OpenApiParameter(name="date_to", description="Fin de période (YYYY-MM-DD)", required=True, type=str),
        ],
        tags=["Fiscal"],
    )
    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="Aucun tenant actif.")

        from datetime import date as date_type
        date_from_str = request.query_params.get("date_from")
        date_to_str = request.query_params.get("date_to")

        if not date_from_str or not date_to_str:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message="Les paramètres date_from et date_to sont requis (YYYY-MM-DD).",
            )

        try:
            date_from = date_type.fromisoformat(date_from_str)
            date_to = date_type.fromisoformat(date_to_str)
        except ValueError:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message="Format de date invalide. Utilisez YYYY-MM-DD.",
            )

        if date_from > date_to:
            return ErrorResponse(
                error_code=ErrorCode.BAD_REQUEST,
                message="date_from doit être antérieure ou égale à date_to.",
            )

        data = build_fiscal_report(tenant, date_from, date_to)
        return SuccessResponse(data=data)
