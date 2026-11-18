"""
Production service: complete a production run, post stock movements.

Flow on completion:
1. Validate status is DRAFT or IN_PROGRESS.
2. For each run line: issue actual_qty from stock (production_issue, negative qty_delta).
   unit_cost = current WAC for that item.
3. Compute cost per packet = (sum material costs + overheads) / actual_good_output.
4. Post FG output (production_output, positive qty_delta) at cost_per_packet.
5. Mark run COMPLETED with completed_at.
6. Write AuditLog.

Benchmark note:
  Pouches: BOM says 200 per batch. Actual run: 188 good packets + 6 damaged.
  Total pouches consumed = 194 (188 good packets × 1 pouch each + 6 damaged).
  We record actual_qty = 194 on the pouch run line.
  Closing balance = 500 - 194 = 306. ✓
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone


def complete_production_run(run, user) -> None:
    """Post all stock movements for a completed production run."""
    from apps.production.models import RunStatus
    from services.stock import create_movement, get_weighted_average_cost, InsufficientStockError
    from apps.core.models import AuditLog
    from django.contrib.contenttypes.models import ContentType

    if run.status not in (RunStatus.DRAFT, RunStatus.IN_PROGRESS):
        raise ValueError(f"Cannot complete run in status '{run.status}'")

    with transaction.atomic():
        total_material_cost = 0
        for run_line in run.lines.select_related("bom_line__item").all():
            item = run_line.bom_line.item
            actual_qty = run_line.actual_qty
            unit_cost = get_weighted_average_cost(item.id)

            create_movement(
                item=item,
                movement_type="production_issue",
                qty_delta=-actual_qty,
                unit_cost_paise=unit_cost,
                source_obj=run,
                user=user,
                notes=f"Production run #{run.id}",
            )
            total_material_cost += int(actual_qty * unit_cost)

        overhead_total = sum(o.amount_paise for o in run.overheads.all())
        total_cost = total_material_cost + overhead_total
        cost_per_packet = (
            int(Decimal(total_cost) / run.actual_good_output)
            if run.actual_good_output
            else 0
        )

        fg_item = run.bom.product
        create_movement(
            item=fg_item,
            movement_type="production_output",
            qty_delta=run.actual_good_output,
            unit_cost_paise=cost_per_packet,
            source_obj=run,
            user=user,
            notes=f"Production run #{run.id}: {run.actual_good_output} good packets",
        )

        run.status = RunStatus.COMPLETED
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at"])

        ct = ContentType.objects.get_for_model(run)
        AuditLog.objects.create(
            content_type=ct, object_id=run.id, action="update", user=user,
            after_json={
                "status": "completed",
                "actual_good_output": str(run.actual_good_output),
                "cost_per_packet_paise": cost_per_packet,
                "cost_per_packet_rupees": f"{Decimal(cost_per_packet)/100:.2f}",
            },
        )
