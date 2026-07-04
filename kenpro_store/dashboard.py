"""
Tableau de bord tenant — agrégats temps réel (F-24 à F-27).
"""
from datetime import timedelta

from django.db.models import Count, DecimalField, ExpressionWrapper, F, FloatField, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from crm.models import Customer
from inventory.models import Product, StockLevel
from repair.models import RepairTicket
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
            "product_name": r["product__name"],
            "sku": r["product__sku"],
            "quantity": float(r["qty_sold"]),
            "amount": str(round(float(r["revenue"]), 2)),
        }
        for r in rows
    ]


def _recent_sales(tenant, limit=6, location=None):
    qs = Sale.objects.filter(tenant=tenant).select_related("customer")
    if location is not None:
        qs = qs.filter(location=location)
    rows = qs.order_by("-created_at")[:limit]
    return [
        {
            "id": str(s.id),
            "reference": s.reference or str(s.id)[:8].upper(),
            "status": s.status,
            "total_amount": str(s.total),
            "customer_name": s.customer.name if s.customer else None,
            "created_at": s.created_at.isoformat(),
        }
        for s in rows
    ]


def build_dashboard(tenant, location=None) -> dict:
    day_start = _period_start("day")
    week_start = _period_start("week")
    month_start = _period_start("month")

    sales_today_qs = Sale.objects.filter(
        tenant=tenant,
        status=Sale.Status.VALIDATED,
        validated_at__gte=day_start,
    )
    if location:
        sales_today_qs = sales_today_qs.filter(location=location)
    sales_today_count = sales_today_qs.count()
    sales_today_amount = _ca(tenant, day_start, location)

    low_stock_count = StockLevel.objects.filter(
        tenant=tenant,
        reorder_threshold__gt=0,
        quantity__lte=F("reorder_threshold"),
    )
    if location:
        low_stock_count = low_stock_count.filter(location=location)
    low_stock_count = low_stock_count.count()

    pending_repairs = RepairTicket.objects.filter(
        tenant=tenant,
    ).exclude(status__in=["delivered", "cancelled"]).count()

    return {
        "location": {"id": str(location.id), "name": location.name} if location else None,
        # Clés attendues par le frontend
        "sales_today": sales_today_count,
        "sales_today_amount": str(sales_today_amount),
        "customers_count": Customer.objects.filter(tenant=tenant).count(),
        "products_count": Product.objects.filter(tenant=tenant, status=Product.ACTIVE).count(),
        "low_stock_count": low_stock_count,
        "pending_repairs": pending_repairs,
        "recent_sales": _recent_sales(tenant, location=location),
        "top_products": _top_products(tenant, month_start, location=location),
        # Détail complet pour usage futur
        "revenue": {
            "today": str(_ca(tenant, day_start, location)),
            "this_week": str(_ca(tenant, week_start, location)),
            "this_month": str(_ca(tenant, month_start, location)),
        },
        "margin": {
            "today": _margin(tenant, day_start, location),
            "this_week": _margin(tenant, week_start, location),
            "this_month": _margin(tenant, month_start, location),
        },
        "cash_collected_today": str(_cash_balance(tenant, day_start, location)),
        "total_customer_debt": str(_total_debt(tenant)),
    }
