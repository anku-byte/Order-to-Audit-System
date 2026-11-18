from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponse
from apps.core.mixins import role_required
from apps.sales.models import Invoice
from apps.inventory.models import Item
from apps.production.models import ProductionRun
from apps.purchasing.models import Purchase
from decimal import Decimal
import csv
from datetime import date


def _date_range(request):
    today = date.today()
    from_date = request.GET.get("from_date", today.replace(day=1).isoformat())
    to_date = request.GET.get("to_date", today.isoformat())
    return from_date, to_date


@login_required
@role_required("admin", "accountant", "owner")
def reports_home(request):
    return render(request, "reports/home.html")


@login_required
@role_required("admin", "accountant", "owner")
def sales_register(request):
    from_date, to_date = _date_range(request)
    invoices = (
        Invoice.objects.filter(status="posted", invoice_date__gte=from_date, invoice_date__lte=to_date)
        .select_related("customer").prefetch_related("lines__item")
        .order_by("invoice_date", "invoice_number")
    )
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="sales_register.csv"'
        w = csv.writer(response)
        w.writerow(["Invoice No","Date","Customer","Supply Type","Taxable ₹","CGST ₹","SGST ₹","IGST ₹","Total ₹"])
        for inv in invoices:
            w.writerow([inv.invoice_number, inv.invoice_date, inv.customer.name, inv.supply_type,
                        f"{inv.taxable_value_paise/100:.2f}", f"{inv.cgst_paise/100:.2f}",
                        f"{inv.sgst_paise/100:.2f}", f"{inv.igst_paise/100:.2f}",
                        f"{inv.total_paise/100:.2f}"])
        return response
    totals = {k: sum(getattr(i, k) for i in invoices) / 100
              for k in ["taxable_value_paise","cgst_paise","sgst_paise","igst_paise","total_paise"]}
    return render(request, "reports/sales_register.html", {
        "invoices": invoices, "totals": totals, "from_date": from_date, "to_date": to_date
    })


@login_required
@role_required("admin", "accountant", "owner")
def gst_summary(request):
    from_date, to_date = _date_range(request)
    invoices = Invoice.objects.filter(status="posted", invoice_date__gte=from_date,
                                      invoice_date__lte=to_date).select_related("customer")
    intrastate = invoices.filter(supply_type="intrastate")
    interstate = invoices.filter(supply_type="interstate")

    def totals(qs):
        return {
            "taxable": sum(i.taxable_value_paise for i in qs) / 100,
            "cgst": sum(i.cgst_paise for i in qs) / 100,
            "sgst": sum(i.sgst_paise for i in qs) / 100,
            "igst": sum(i.igst_paise for i in qs) / 100,
            "total": sum(i.total_paise for i in qs) / 100,
        }

    return render(request, "reports/gst_summary.html", {
        "intrastate": intrastate, "intrastate_totals": totals(intrastate),
        "interstate": interstate, "interstate_totals": totals(interstate),
        "from_date": from_date, "to_date": to_date,
    })


@login_required
@role_required("admin", "accountant", "owner")
def stock_report(request):
    from services.stock import get_balance, get_weighted_average_cost
    items_data = []
    for item in Item.objects.filter(is_active=True).order_by("category","name"):
        balance = get_balance(item.id)
        wac = get_weighted_average_cost(item.id)
        items_data.append({
            "item": item, "balance": balance,
            "wac_rupees": Decimal(wac)/100,
            "value_rupees": Decimal(int(balance*wac))/100,
        })
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="stock_summary.csv"'
        w = csv.writer(response)
        w.writerow(["Item","Category","Unit","Balance","WAC ₹","Value ₹"])
        for d in items_data:
            w.writerow([d["item"].name, d["item"].get_category_display(),
                        d["item"].base_unit, d["balance"],
                        f"{d['wac_rupees']:.2f}", f"{d['value_rupees']:.2f}"])
        return response
    return render(request, "reports/stock_report.html", {"items_data": items_data})


@login_required
@role_required("admin", "accountant", "owner", "production")
def production_report(request):
    from_date, to_date = _date_range(request)
    runs = (
        ProductionRun.objects.filter(run_date__gte=from_date, run_date__lte=to_date)
        .select_related("bom__product")
        .prefetch_related("lines__bom_line__item", "overheads")
    )
    return render(request, "reports/production_report.html", {
        "runs": runs, "from_date": from_date, "to_date": to_date
    })


@login_required
@role_required("admin", "accountant", "owner")
def outstanding_report(request):
    from services.sales import get_outstanding_by_customer
    # Ageing buckets: 0-30, 31-60, 61-90, 90+
    from apps.sales.models import Invoice, PaymentAllocation
    from django.db.models import Sum
    today = date.today()
    data = []
    for customer in __import__("apps.sales.models", fromlist=["Customer"]).Customer.objects.filter(is_active=True):
        posted_invoices = Invoice.objects.filter(customer=customer, status="posted")
        buckets = {"0_30": 0, "31_60": 0, "61_90": 0, "over_90": 0}
        total_outstanding = 0
        for inv in posted_invoices:
            outstanding = inv.outstanding_paise
            if outstanding <= 0:
                continue
            age = (today - inv.invoice_date).days
            total_outstanding += outstanding
            if age <= 30:
                buckets["0_30"] += outstanding
            elif age <= 60:
                buckets["31_60"] += outstanding
            elif age <= 90:
                buckets["61_90"] += outstanding
            else:
                buckets["over_90"] += outstanding
        if total_outstanding > 0:
            data.append({
                "customer": customer,
                "outstanding_paise": total_outstanding,
                "outstanding_rupees": Decimal(total_outstanding)/100,
                "buckets": {k: Decimal(v)/100 for k,v in buckets.items()},
            })
    return render(request, "reports/outstanding.html", {"data": data})


@login_required
@role_required("admin", "accountant", "owner")
def purchase_report(request):
    from_date, to_date = _date_range(request)
    purchases = (
        Purchase.objects.filter(purchase_date__gte=from_date, purchase_date__lte=to_date,
                                status="posted")
        .select_related("supplier")
        .prefetch_related("lines__item")
    )
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="purchase_register.csv"'
        w = csv.writer(response)
        w.writerow(["Purchase#","Date","Supplier","Item","Qty","Unit","Unit Price ₹","Total ₹"])
        for p in purchases:
            for line in p.lines.all():
                w.writerow([p.id, p.purchase_date, p.supplier.name, line.item.name,
                            line.qty, line.unit, f"{line.unit_price_paise/100:.2f}",
                            f"{line.total_paise/100:.2f}"])
        return response
    return render(request, "reports/purchase_report.html", {
        "purchases": purchases, "from_date": from_date, "to_date": to_date
    })
