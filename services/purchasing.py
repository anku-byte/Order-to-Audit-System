"""Purchasing service: create draft purchase, post to stock."""
from decimal import Decimal
from django.db import transaction


def create_purchase(post_data, user):
    from apps.purchasing.models import Purchase, PurchaseLine
    from apps.inventory.models import Item
    from services.units import to_base_unit

    supplier_id = post_data.get("supplier")
    item_ids = post_data.getlist("item_id")
    qtys = post_data.getlist("qty")
    units = post_data.getlist("unit")
    prices = post_data.getlist("unit_price_paise")
    purchase_date = post_data.get("purchase_date")

    with transaction.atomic():
        purchase = Purchase.objects.create(
            supplier_id=supplier_id, purchase_date=purchase_date,
            invoice_ref=post_data.get("invoice_ref", ""),
            status="draft", created_by=user,
        )
        for item_id, qty, unit, price in zip(item_ids, qtys, units, prices):
            if item_id and qty and Decimal(qty) > 0:
                item = Item.objects.get(id=item_id)
                qty_d = Decimal(qty)
                qty_base, _ = to_base_unit(qty_d, unit, item)
                total = int(qty_base * int(price))
                PurchaseLine.objects.create(
                    purchase=purchase, item=item, qty=qty_d, unit=unit,
                    unit_price_paise=int(price), qty_in_base=qty_base, total_paise=total,
                )
    return purchase


def post_purchase(purchase, user) -> None:
    """Post purchase: create StockMovement rows using WAC logic."""
    from services.stock import create_movement
    from apps.core.models import AuditLog
    from django.contrib.contenttypes.models import ContentType

    if purchase.status != "draft":
        raise ValueError(f"Purchase #{purchase.id} is already posted.")

    with transaction.atomic():
        for line in purchase.lines.select_related("item").all():
            # unit cost per BASE unit = total_paise / qty_in_base
            if line.qty_in_base > 0:
                unit_cost = int(Decimal(line.total_paise) / line.qty_in_base)
            else:
                unit_cost = line.unit_price_paise

            create_movement(
                item=line.item, movement_type="purchase",
                qty_delta=line.qty_in_base, unit_cost_paise=unit_cost,
                source_obj=purchase, user=user,
                notes=f"Purchase #{purchase.id} from {purchase.supplier.name}",
            )

        purchase.status = "posted"
        purchase.save(update_fields=["status"])

        ct = ContentType.objects.get_for_model(purchase)
        AuditLog.objects.create(
            content_type=ct, object_id=purchase.id, action="post", user=user,
            after_json={"status": "posted"},
        )
