"""
Rapport fiscal légal (Option 2 — optimisation fiscale réelle).

Calcule les postes déductibles légaux pour aider le tenant à déclarer
un bénéfice imposable juste :

  CA brut            = Σ Sale.total (ventes validées sur la période)
  Avoirs             = Σ CreditNote.total (retours / annulations)
  CA net             = CA brut − avoirs
  CMV                = Σ Product.cost × SaleLine.quantity (coût des marchandises vendues)
  Pertes de stock    = Σ quantity × cost sur les mouvements de type LOSS
  Bénéfice brut est. = CA net − CMV − pertes de stock

Aucune donnée n'est falsifiée. Toutes les valeurs correspondent aux
transactions réelles enregistrées dans le système.
"""
from datetime import date

from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce

from inventory.models import StockMovement
from sales.models import CreditNote, Sale, SaleLine


def _dec(value):
    """Garantit un Decimal, jamais None."""
    from decimal import Decimal
    return value if value is not None else Decimal("0")


def build_fiscal_report(tenant, date_from: date, date_to: date) -> dict:
    """
    Retourne le rapport d'optimisation fiscale pour la période [date_from, date_to].
    Les dates sont inclusives (filtre sur validated_at / created_at).
    """
    from django.utils.timezone import make_aware
    from datetime import datetime, time

    start = make_aware(datetime.combine(date_from, time.min))
    end = make_aware(datetime.combine(date_to, time.max))

    # ------------------------------------------------------------------ #
    # 1. CA brut — ventes validées sur la période
    # ------------------------------------------------------------------ #
    gross_revenue = _dec(
        Sale.objects.filter(
            tenant=tenant,
            status=Sale.Status.VALIDATED,
            validated_at__range=(start, end),
        ).aggregate(v=Coalesce(Sum("total"), 0, output_field=DecimalField()))["v"]
    )

    # ------------------------------------------------------------------ #
    # 2. Avoirs — retours / annulations partielles
    # ------------------------------------------------------------------ #
    credit_notes_total = _dec(
        CreditNote.objects.filter(
            tenant=tenant,
            created_at__range=(start, end),
            sale__status="validated",
        ).aggregate(v=Coalesce(Sum("total"), 0, output_field=DecimalField()))["v"]
    )

    net_revenue = gross_revenue - credit_notes_total

    # ------------------------------------------------------------------ #
    # 3. Coût des marchandises vendues (CMV)
    #    = Σ product.cost × quantity pour les lignes des ventes validées
    # ------------------------------------------------------------------ #
    cogs = _dec(
        SaleLine.objects.filter(
            tenant=tenant,
            sale__status=Sale.Status.VALIDATED,
            sale__validated_at__range=(start, end),
        ).annotate(
            line_cost=ExpressionWrapper(
                F("product__cost") * F("quantity"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ).aggregate(v=Coalesce(Sum("line_cost"), 0, output_field=DecimalField()))["v"]
    )

    # ------------------------------------------------------------------ #
    # 4. Pertes de stock déclarées (type LOSS)
    #    Valorisées au coût d'achat du produit
    # ------------------------------------------------------------------ #
    stock_losses = _dec(
        StockMovement.objects.filter(
            tenant=tenant,
            type=StockMovement.LOSS,
            created_at__range=(start, end),
        ).annotate(
            loss_value=ExpressionWrapper(
                F("quantity") * F("product__cost"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ).aggregate(v=Coalesce(Sum("loss_value"), 0, output_field=DecimalField()))["v"]
    )

    # ------------------------------------------------------------------ #
    # 5. Bénéfice brut estimé (avant charges d'exploitation non trackées)
    # ------------------------------------------------------------------ #
    gross_profit = net_revenue - cogs - stock_losses

    # ------------------------------------------------------------------ #
    # 6. Détail avoirs par motif
    # ------------------------------------------------------------------ #
    credit_notes_by_reason = list(
        CreditNote.objects.filter(
            tenant=tenant,
            created_at__range=(start, end),
        )
        .values("reason")
        .annotate(
            count=Sum(F("id") * 0 + 1),  # COUNT(*)
            total=Coalesce(Sum("total"), 0, output_field=DecimalField()),
        )
        .order_by("-total")
    )

    # ------------------------------------------------------------------ #
    # 7. Top pertes de stock par produit
    # ------------------------------------------------------------------ #
    top_losses = list(
        StockMovement.objects.filter(
            tenant=tenant,
            type=StockMovement.LOSS,
            created_at__range=(start, end),
        )
        .values("product__id", "product__name", "product__sku")
        .annotate(
            qty_lost=Coalesce(Sum("quantity"), 0, output_field=DecimalField()),
            value_lost=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("quantity") * F("product__cost"),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                ),
                0,
                output_field=DecimalField(),
            ),
        )
        .order_by("-value_lost")[:10]
    )

    return {
        "period": {
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
        },
        "revenue": {
            "gross": gross_revenue,
            "credit_notes": credit_notes_total,
            "net": net_revenue,
        },
        "deductions": {
            "cost_of_goods_sold": cogs,
            "stock_losses": stock_losses,
            "total": cogs + stock_losses,
        },
        "gross_profit_estimate": gross_profit,
        "details": {
            "credit_notes_by_reason": credit_notes_by_reason,
            "top_stock_losses": [
                {
                    "product_id": str(r["product__id"]),
                    "name": r["product__name"],
                    "sku": r["product__sku"],
                    "qty_lost": float(r["qty_lost"]),
                    "value_lost": float(r["value_lost"]),
                }
                for r in top_losses
            ],
        },
    }
