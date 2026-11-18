from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from apps.inventory.models import Item
from services.stock import get_balance
from decimal import Decimal


@login_required
def dashboard(request):
    from apps.sales.models import Order, Invoice, Payment
    from apps.production.models import ProductionRun, ProductionRunLine

    # Low stock alerts
    low_stock = []
    for item in Item.objects.filter(is_active=True):
        balance = get_balance(item.id)
        if item.reorder_level and balance < item.reorder_level:
            low_stock.append({"item": item, "balance": balance})

    pending_orders = Order.objects.filter(status="submitted").count()
    recent_runs = ProductionRun.objects.select_related("bom__product").order_by("-created_at")[:5]

    # Variance flags
    flagged_lines = (
        ProductionRunLine.objects.filter(is_flagged=True)
        .select_related("run__bom__product", "bom_line__item")
        .order_by("-run__run_date")[:10]
    )

    # Outstanding summary
    from services.sales import get_outstanding_by_customer
    outstanding = get_outstanding_by_customer()
    total_outstanding = sum(d["outstanding_paise"] for d in outstanding)

    return render(request, "core/dashboard.html", {
        "low_stock": low_stock,
        "pending_orders": pending_orders,
        "recent_runs": recent_runs,
        "flagged_lines": flagged_lines,
        "outstanding_rupees": Decimal(total_outstanding) / 100,
    })
