"""
Tableau de bord tenant — agrégats temps réel (F-24 à F-27).

Calculs :
  - CA       : somme Sale.total (ventes validées sur la période)
  - Marge    : somme (SaleLine.final_price - Product.cost) × quantity
  - Caisse   : somme Payment.amount excluant CREDIT (paiements confirmés du jour)
  - Dettes   : somme Customer.debt_balance > 0 pour le tenant
  - Top ventes : produits classés par quantité vendue (période glissante)
"""
from datetime import timedelta

from django.db.models import DecimalField, ExpressionWrapper, F, FloatField, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from crm.models import Customer
from sales.models import Payment, Sale, SaleLine


def _period_start(period: str):
    now = timezone.now()
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Période inconnue : {period!r}")


def _ca(tenant, since, location=None):
    qs = Sale.objects.filter(
        tenant=tenant,
        status=Sale.Status.VALIDATED,
        validated_at__gte=since,
    )
    if location is not None:
        qs = qs.filter(location=location)
    return qs.aggregate(total=Coalesce(Sum("total"), 0, output_field=DecimalField()))["total"]


def _margin(tenant, since, location=None):
    """
    Marge brute = Σ (final_price - product.cost) × quantity.
    Utilise le coût courant du produit (pas de snapshot historique en base).
    """
    qs = SaleLine.objects.filter(
        tenant=tenant,
        sale__status=Sale.Status.VALIDATED,
        sale__validated_at__gte=since,
    )
    if location is not None:
        qs = qs.filter(sale__location=location)
    return qs.annotate(
        line_margin=ExpressionWrapper(
            (F("final_price") - F("product__cost")) * F("quantity"),
            output_field=FloatField(),
        )
    ).aggregate(total=Coalesce(Sum("line_margin"), 0.0))["total"]


def _cash_balance(tenant, since, location=None):
    """Encaissements réels du jour (hors crédit client)."""
    qs = Payment.objects.filter(
        tenant=tenant,
        status=Payment.Status.CONFIRMED,
        created_at__gte=since,
    ).exclude(method=Payment.Method.CREDIT)
    if location is not None:
        qs = qs.filter(sale__location=location)
    return qs.aggregate(total=Coalesce(Sum("amount"), 0, output_field=DecimalField()))["total"]


def _total_debt(tenant):
    return Customer.objects.filter(tenant=tenant, debt_balance__gt=0).aggregate(
        total=Coalesce(Sum("debt_balance"), 0, output_field=DecimalField())
    )["total"]


def _top_products(tenant, since, limit=5, location=None):
    qs = SaleLine.objects.filter(
        tenant=tenant,
        sale__status=Sale.Status.VALIDATED,
        sale__validated_at__gte=since,
    )
    if location is not None:
        qs = qs.filter(sale__location=location)
    rows = (
        qs.values("product__id", "product__name", "product__sku")
        .annotate(qty_sold=Sum("quantity"), revenue=Sum(F("final_price") * F("quantity")))
        .order_by("-qty_sold")[:limit]
    )
    return [
        {
            "product_id": str(r["product__id"]),
            "name": r["product__name"],
            "sku": r["product__sku"],
            "qty_sold": float(r["qty_sold"]),
            "revenue": float(r["revenue"]),
        }
        for r in rows
    ]


def build_dashboard(tenant, location=None) -> dict:
    """
    Retourne le tableau de bord pour un tenant (global ou filtré par boutique).
    Passer `location` (instance Location) pour les stats d'une boutique précise.
    """
    day_start = _period_start("day")
    week_start = _period_start("week")
    month_start = _period_start("month")

    return {
        "location": {"id": str(location.id), "name": location.name} if location else None,
        "revenue": {
            "today": _ca(tenant, day_start, location),
            "this_week": _ca(tenant, week_start, location),
            "this_month": _ca(tenant, month_start, location),
        },
        "margin": {
            "today": _margin(tenant, day_start, location),
            "this_week": _margin(tenant, week_start, location),
            "this_month": _margin(tenant, month_start, location),
        },
        "cash_collected_today": _cash_balance(tenant, day_start, location),
        "total_customer_debt": _total_debt(tenant),
        "top_products_this_month": _top_products(tenant, month_start, location=location),
    }
