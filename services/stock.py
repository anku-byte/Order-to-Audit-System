"""
Stock ledger service.

Balance = SUM(qty_delta) on StockMovement. Never a stored field.

Weighted Average Cost (WAC):
  On each inward movement: new_avg = (old_qty*old_avg + new_qty*new_cost) / (old_qty+new_qty)
  WHY WAC: smooths price volatility, easy to audit (one number per item), and is the
  standard method under IndAS 2 for food manufacturers who don't track batches strictly.
  FIFO would require batch matching; LIFO is prohibited under IndAS; WAC is simplest
  and most defensible for this business.

All stock-modifying operations use select_for_update on the Item row
to prevent race conditions (concurrent approval/dispatch).
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from django.db import transaction
from django.db.models import Sum


class InsufficientStockError(Exception):
    pass


def get_balance(item_id: int, as_of=None) -> Decimal:
    """Current balance for item in its base unit."""
    from apps.inventory.models import StockMovement
    qs = StockMovement.objects.filter(item_id=item_id)
    if as_of:
        qs = qs.filter(created_at__lte=as_of)
    result = qs.aggregate(total=Sum("qty_delta"))["total"]
    return result if result is not None else Decimal("0")


def get_weighted_average_cost(item_id: int) -> int:
    """
    Current WAC per base unit in paise.
    Scans all inward movements chronologically and applies the WAC formula cumulatively.
    Returns 0 if no inward movements.
    """
    from apps.inventory.models import StockMovement
    inward_types = ["opening", "purchase", "production_output", "return"]
    movements = (
        StockMovement.objects
        .filter(item_id=item_id, qty_delta__gt=0, movement_type__in=inward_types)
        .order_by("created_at", "id")
    )
    running_qty = Decimal("0")
    running_avg = Decimal("0")
    for m in movements:
        new_qty = m.qty_delta
        new_cost = Decimal(m.unit_cost)
        denom = running_qty + new_qty
        if denom > 0:
            running_avg = (running_qty * running_avg + new_qty * new_cost) / denom
        running_qty += new_qty
    return int(running_avg.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def create_movement(
    item,
    movement_type: str,
    qty_delta: Decimal,
    unit_cost_paise: int,
    source_obj=None,
    user=None,
    batch_no: str = "",
    expiry_date=None,
    notes: str = "",
):
    """
    Create a StockMovement inside a transaction.
    For outgoing (qty_delta < 0): validates balance won't go negative.
    Uses select_for_update on Item to prevent race conditions.
    """
    from apps.inventory.models import StockMovement, Item as ItemModel
    from django.contrib.contenttypes.models import ContentType

    with transaction.atomic():
        ItemModel.objects.select_for_update().get(id=item.id)

        if qty_delta < 0:
            balance = get_balance(item.id)
            if balance + qty_delta < Decimal("0"):
                raise InsufficientStockError(
                    f"Insufficient stock for {item.name}: "
                    f"available {balance} {item.base_unit}, "
                    f"requested {abs(qty_delta)} {item.base_unit}"
                )

        value = int(qty_delta * unit_cost_paise)

        source_ct = None
        source_oid = None
        if source_obj is not None:
            source_ct = ContentType.objects.get_for_model(source_obj)
            source_oid = source_obj.pk

        return StockMovement.objects.create(
            item=item,
            movement_type=movement_type,
            qty_delta=qty_delta,
            unit_cost=unit_cost_paise,
            value=value,
            batch_no=batch_no or "",
            expiry_date=expiry_date,
            source_content_type=source_ct,
            source_object_id=source_oid,
            created_by=user,
            notes=notes,
        )


def get_ledger(item_id: int, from_date=None, to_date=None):
    """Return ordered StockMovement queryset for running balance computation."""
    from apps.inventory.models import StockMovement
    qs = StockMovement.objects.filter(item_id=item_id).select_related(
        "created_by", "source_content_type"
    )
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)
    return qs.order_by("created_at", "id")
