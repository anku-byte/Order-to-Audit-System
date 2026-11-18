from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from decimal import Decimal
from .models import Item, StockMovement
from services.stock import get_balance, get_ledger, get_weighted_average_cost


@login_required
def stock_summary(request):
    items_data = []
    for item in Item.objects.filter(is_active=True).order_by("category", "name"):
        balance = get_balance(item.id)
        wac = get_weighted_average_cost(item.id)
        value_rupees = Decimal(int(balance * wac)) / 100
        items_data.append({
            "item": item,
            "balance": balance,
            "wac_rupees": Decimal(wac) / 100,
            "value_rupees": value_rupees,
            "below_reorder": bool(item.reorder_level and balance < item.reorder_level),
        })
    return render(request, "inventory/stock_summary.html", {"items_data": items_data})


@login_required
def stock_ledger(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    from_date = request.GET.get("from_date")
    to_date = request.GET.get("to_date")
    movements = get_ledger(item_id, from_date, to_date)

    running_balance = Decimal("0")
    ledger_rows = []
    for m in movements:
        running_balance += m.qty_delta
        ledger_rows.append({"movement": m, "running_balance": running_balance})

    return render(request, "inventory/stock_ledger.html", {
        "item": item, "ledger_rows": ledger_rows,
        "from_date": from_date, "to_date": to_date,
        "current_balance": running_balance,
    })


@login_required
def item_list(request):
    items = Item.objects.filter(is_active=True).order_by("category", "name")
    return render(request, "inventory/item_list.html", {"items": items})
