"""Sales service: order approval, invoice creation, dispatch, payment, outstanding."""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone


def create_order(post_data, user):
    from apps.sales.models import Order, OrderLine
    customer_id = post_data.get("customer")
    item_ids = post_data.getlist("item_id")
    qtys = post_data.getlist("qty")
    prices = post_data.getlist("unit_price_paise")

    with transaction.atomic():
        order = Order.objects.create(
            customer_id=customer_id, salesman=user, status="submitted",
            notes=post_data.get("notes", ""),
        )
        for item_id, qty, price in zip(item_ids, qtys, prices):
            if item_id and qty and Decimal(qty) > 0:
                OrderLine.objects.create(
                    order=order, item_id=item_id,
                    qty=Decimal(qty), unit_price_paise=int(price),
                )
    return order


def approve_order(order, user):
    """Approve order: create GST invoice, dispatch FG stock, return Invoice."""
    from apps.sales.models import Order, Invoice, InvoiceLine, Dispatch, DispatchLine, _current_fy
    from services.gst import compute_invoice_gst
    from services.stock import create_movement, get_weighted_average_cost
    from apps.core.models import AuditLog
    from django.contrib.contenttypes.models import ContentType
    from datetime import date

    if order.status != "submitted":
        raise ValueError(f"Order #{order.id} is not SUBMITTED (is '{order.status}')")

    with transaction.atomic():
        lines_data = [
            {"item": line.item, "qty": line.qty, "unit_price_paise": line.unit_price_paise}
            for line in order.lines.select_related("item").all()
        ]
        gst = compute_invoice_gst(order.customer, lines_data)
        fy = _current_fy()

        invoice = Invoice.objects.create(
            order=order, customer=order.customer,
            invoice_date=date.today(), fy=fy, status="draft",
            supply_type=gst.supply_type,
            taxable_value_paise=gst.total_taxable_paise,
            cgst_paise=gst.total_cgst_paise,
            sgst_paise=gst.total_sgst_paise,
            igst_paise=gst.total_igst_paise,
            total_paise=gst.grand_total_paise,
            created_by=user,
        )

        order_lines = list(order.lines.select_related("item").all())
        for order_line, gst_line in zip(order_lines, gst.lines):
            InvoiceLine.objects.create(
                invoice=invoice, item=order_line.item,
                hsn_code=order_line.item.hsn_code,
                qty=order_line.qty,
                unit_price_paise=order_line.unit_price_paise,
                taxable_value_paise=gst_line.taxable_value_paise,
                gst_rate=gst_line.gst_rate,
                cgst_paise=gst_line.cgst_paise,
                sgst_paise=gst_line.sgst_paise,
                igst_paise=gst_line.igst_paise,
            )

        invoice.post()

        dispatch = Dispatch.objects.create(
            invoice=invoice, dispatch_date=date.today(), created_by=user,
        )
        for inv_line in invoice.lines.select_related("item").all():
            DispatchLine.objects.create(
                dispatch=dispatch, invoice_line=inv_line, qty_dispatched=inv_line.qty,
            )
            fg_wac = get_weighted_average_cost(inv_line.item_id)
            create_movement(
                item=inv_line.item,
                movement_type="sale_dispatch",
                qty_delta=-inv_line.qty,
                unit_cost_paise=fg_wac,
                source_obj=dispatch,
                user=user,
                notes=f"Invoice {invoice.invoice_number}",
            )

        order.status = "dispatched"
        order.approved_by = user
        order.approved_at = timezone.now()
        order.save(update_fields=["status", "approved_by", "approved_at"])

        ct = ContentType.objects.get_for_model(order)
        AuditLog.objects.create(
            content_type=ct, object_id=order.id, action="approve", user=user,
            after_json={"status": "dispatched", "invoice_number": invoice.invoice_number},
        )

    return invoice


def record_payment(post_data, user):
    from apps.sales.models import Payment, PaymentAllocation
    from datetime import date

    customer_id = post_data.get("customer")
    amount_paise = int(post_data.get("amount_paise", 0))
    mode = post_data.get("mode", "cash")
    reference = post_data.get("reference", "")
    invoice_ids = post_data.getlist("invoice_id")
    alloc_amounts = post_data.getlist("alloc_amount_paise")

    with transaction.atomic():
        payment = Payment.objects.create(
            customer_id=customer_id, payment_date=date.today(),
            amount_paise=amount_paise, mode=mode, reference=reference, created_by=user,
        )
        for inv_id, alloc in zip(invoice_ids, alloc_amounts):
            if inv_id and alloc and int(alloc) > 0:
                PaymentAllocation.objects.create(
                    payment=payment, invoice_id=inv_id, allocated_paise=int(alloc),
                )
    return payment


def get_outstanding_by_customer() -> list:
    from apps.sales.models import Customer, Invoice, PaymentAllocation
    from django.db.models import Sum

    result = []
    for customer in Customer.objects.filter(is_active=True):
        total_invoiced = (
            Invoice.objects.filter(customer=customer, status="posted")
            .aggregate(t=Sum("total_paise"))["t"] or 0
        )
        total_paid = (
            PaymentAllocation.objects.filter(invoice__customer=customer)
            .aggregate(t=Sum("allocated_paise"))["t"] or 0
        )
        outstanding = total_invoiced - total_paid
        if total_invoiced > 0:
            result.append({
                "customer": customer,
                "total_invoiced_paise": total_invoiced,
                "total_paid_paise": total_paid,
                "outstanding_paise": outstanding,
                "outstanding_rupees": Decimal(outstanding) / 100,
            })
    return result
