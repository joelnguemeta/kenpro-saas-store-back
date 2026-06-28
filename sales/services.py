"""
Couche service de l'app `sales`.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from inventory.models import StockMovement
from inventory.services import StockLedger

from .models import CreditNote, CreditNoteLine, Payment, Sale, SaleLine


@dataclass
class ReturnLine:
    """Décrit une ligne à retourner dans un avoir."""
    sale_line_id: str   # UUID de la SaleLine d'origine
    quantity: Decimal


class CreditNoteService:
    """
    Émet un avoir sur une vente validée (F-12).

    Un avoir peut être partiel : seules les lignes passées dans `lines` sont
    retournées. Le service :
      1. Valide les quantités (pas de retour > vendu)
      2. Crée le CreditNote et ses CreditNoteLines
      3. Enregistre les entrées de stock correspondantes
      4. Réduit la dette client si la vente comportait des paiements CREDIT
    """

    @classmethod
    @transaction.atomic
    def create(
        cls,
        *,
        sale: Sale,
        lines: list[ReturnLine],
        reason: str = CreditNote.Reason.OTHER,
        note: str = "",
        created_by,
    ) -> CreditNote:
        if sale.status != Sale.Status.VALIDATED:
            raise ValueError("Un avoir ne peut être émis que sur une vente validée.")
        if not lines:
            raise ValueError("Un avoir doit comporter au moins une ligne.")

        # Charge les SaleLines d'origine indexées par ID
        sale_line_ids = [l.sale_line_id for l in lines]
        sale_lines = {
            str(sl.id): sl
            for sl in SaleLine.objects.select_related("product").filter(
                sale=sale, id__in=sale_line_ids
            )
        }

        missing = set(sale_line_ids) - set(sale_lines)
        if missing:
            raise ValueError(f"Lignes introuvables sur cette vente : {missing}")

        # Numéro d'avoir séquentiel par tenant — SELECT FOR UPDATE évite la race condition.
        last_ref = (
            CreditNote.objects.select_for_update()
            .filter(tenant=sale.tenant, reference__startswith="AV-")
            .order_by("-reference")
            .values_list("reference", flat=True)
            .first()
        )
        next_num = (int(last_ref.split("-")[1]) + 1) if last_ref else 1
        reference = f"AV-{next_num:06d}"

        credit_note = CreditNote.objects.create(
            tenant=sale.tenant,
            sale=sale,
            reference=reference,
            reason=reason,
            note=note,
            total=0,
            created_by=created_by,
        )

        total = Decimal("0")
        for ret in lines:
            sl = sale_lines[str(ret.sale_line_id)]
            cn_line = CreditNoteLine(
                tenant=sale.tenant,
                credit_note=credit_note,
                sale_line=sl,
                quantity=ret.quantity,
                unit_price=sl.final_price,
            )
            cn_line.save()
            total += cn_line.line_total

            # Entrée de stock — le retour réintègre les produits
            StockLedger.record_movement(
                tenant=sale.tenant,
                product=sl.product,
                location=sale.location,
                type=StockMovement.IN,
                quantity=ret.quantity,
                unit=sl.unit,
                reason=f"Retour avoir {reference}",
                reference=str(credit_note.id),
                created_by=created_by,
            )

        credit_note.total = total
        credit_note.save(update_fields=["total"])

        # Réduction de la dette si la vente comportait des paiements CREDIT
        cls._reverse_credit_debt(sale, credit_note, created_by=created_by)

        return credit_note

    @staticmethod
    def _reverse_credit_debt(sale: Sale, credit_note: CreditNote, *, created_by) -> None:
        """
        Si la vente originale avait des paiements CREDIT, on réduit
        la dette client à hauteur du montant de l'avoir (plafonnée).
        """
        if not sale.customer_id:
            return

        credit_paid = sum(
            p.amount for p in sale.payments.filter(method=Payment.Method.CREDIT)
        )
        if credit_paid <= 0:
            return

        # On réduit la dette du minimum entre le montant de l'avoir et ce qui avait été mis en crédit
        amount_to_reverse = min(credit_note.total, credit_paid)
        if amount_to_reverse <= 0:
            return

        from crm.services import DebtService
        DebtService.repay(
            sale.customer,
            amount_to_reverse,
            reference=str(credit_note.id),
            note=f"Avoir {credit_note.reference} — annulation partielle crédit",
            recorded_by=created_by,
        )
