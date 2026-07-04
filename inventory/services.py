"""
Stock ledger — logique de cohérence du stock.

Règle d'or : le `StockLevel` n'est jamais écrit en direct par le métier ; il
se recalcule depuis les `StockMovement` (source de vérité, append-only). Une
sortie est enregistrée de façon atomique pour éviter la survente.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from .models import StockLevel, StockMovement


class InsufficientStock(Exception):
    """Levée quand une sortie ferait passer le solde sous zéro (survente)."""


class StockLedger:

    @staticmethod
    def current_quantity(*, product, location, variant=None) -> Decimal:
        """Solde réel recalculé depuis les mouvements (somme des quantités signées)."""
        movements = StockMovement.objects.filter(
            product=product, location=location, variant=variant
        )
        total = Decimal("0")
        for m in movements.only("type", "quantity"):
            total += m.signed_quantity
        return total

    @classmethod
    def recalculate_level(cls, *, tenant, product, location, variant=None) -> StockLevel:
        """Reconstruit la ligne de cache StockLevel à partir des mouvements."""
        quantity = cls.current_quantity(product=product, location=location, variant=variant)
        level, _ = StockLevel.objects.get_or_create(
            tenant=tenant, product=product, location=location, variant=variant,
        )
        level.quantity = quantity
        level.save(update_fields=["quantity", "updated_at"])
        return level

    @classmethod
    @transaction.atomic
    def record_movement(cls, *, tenant, allow_negative=False, **fields) -> StockMovement:
        """
        Enregistre un mouvement immuable puis met à jour le cache StockLevel,
        le tout dans une transaction. Bloque la survente sauf si
        `allow_negative` (ajustements d'inventaire, corrections admin).

        Idempotent sur `client_uuid` : un mouvement déjà synchronisé (même
        client_uuid pour ce tenant) n'est pas réinséré.
        """
        client_uuid = fields.get("client_uuid")
        if client_uuid:
            existing = StockMovement.objects.filter(
                tenant=tenant, client_uuid=client_uuid
            ).first()
            if existing:
                return existing

        product = fields["product"]
        location = fields["location"]
        variant = fields.get("variant")

        # Verrou pessimiste sur la ligne de cache pour sérialiser les sorties
        # concurrentes sur le même (produit, emplacement, variante).
        StockLevel.objects.select_for_update().filter(
            tenant=tenant, product=product, location=location, variant=variant
        ).first()

        movement = StockMovement(tenant=tenant, **fields)

        # Un ajustement d'inventaire porte son propre signe et peut rendre le
        # solde négatif (correction de comptage) — jamais bloqué pour survente.
        if movement.type == StockMovement.ADJUSTMENT:
            allow_negative = True

        if not allow_negative and movement.signed_quantity < 0:
            projected = cls.current_quantity(
                product=product, location=location, variant=variant
            ) + movement.signed_quantity
            if projected < 0:
                raise InsufficientStock(
                    f"Stock insuffisant pour {product} : solde projeté {projected}."
                )

        movement.save()
        cls.recalculate_level(
            tenant=tenant, product=product, location=location, variant=variant
        )
        return movement

    @classmethod
    @transaction.atomic
    def transfer(
        cls,
        *,
        tenant,
        product,
        from_location,
        to_location,
        quantity,
        variant=None,
        unit: str = "unité",
        reason: str = "",
        created_by=None,
    ) -> tuple[StockMovement, StockMovement]:
        """
        Transfert entre deux emplacements : une sortie à la source (survente
        refusée) + une entrée à destination, liées par une référence commune.
        Atomique : tout ou rien.
        """
        import uuid as _uuid

        if from_location == to_location:
            raise ValueError("La source et la destination doivent différer.")
        if quantity is None or Decimal(str(quantity)) <= 0:
            raise ValueError("La quantité doit être positive.")

        transfer_ref = f"TR-{_uuid.uuid4().hex[:10].upper()}"
        label = reason or f"Transfert {from_location.name} → {to_location.name}"

        out_mv = cls.record_movement(
            tenant=tenant,
            product=product,
            variant=variant,
            location=from_location,
            type=StockMovement.OUT,
            quantity=quantity,
            unit=unit,
            reason=label,
            reference=transfer_ref,
            created_by=created_by,
        )
        in_mv = cls.record_movement(
            tenant=tenant,
            product=product,
            variant=variant,
            location=to_location,
            type=StockMovement.IN,
            quantity=quantity,
            unit=unit,
            reason=label,
            reference=transfer_ref,
            created_by=created_by,
        )
        return out_mv, in_mv
