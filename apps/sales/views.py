from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from decimal import Decimal
from .models import Order, Invoice, Payment, Customer
from apps.core.mixins import role_required
from apps.inventory.models import Item
from services.stock import get_balance


@login_required
def order_list(request):
    orders = Order.objects.select_related("customer", "salesman").order_by("-created_at")
    if request.user.role == "salesman":
        orders = orders.filter(salesman=request.user)
    return render(request, "sales/order_list.html", {"orders": orders})


@login_required
def order_create(request):
    customers = Customer.objects.filter(is_active=True)
    items = Item.objects.filter(is_active=True, category="fg")
    if request.method == "POST":
        from services.sales import create_order
        try:
            order = create_order(request.POST, request.user)
            messages.success(request, f"Order #{order.id} submitted.")
            return redirect("order_detail", pk=order.pk)
        except Exception as e:
            messages.error(request, str(e))
    return render(request, "sales/order_create.html", {
        "customers": customers, "items": items
    })


@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer", "salesman"), pk=pk)
    if request.user.role == "salesman" and order.salesman != request.user:
        raise PermissionDenied
    lines = order.lines.select_related("item").all()
    stock_checks = []
    for line in lines:
        balance = get_balance(line.item_id)
        stock_checks.append({
            "line": line,
            "balance": balance,
            "shortage": max(Decimal("0"), line.qty - balance),
        })
    return render(request, "sales/order_detail.html", {
        "order": order, "stock_checks": stock_checks,
    })


@login_required
@role_required("admin", "owner")
def order_approve(request, pk):
    if request.method == "POST":
        from services.sales import approve_order
        order = get_object_or_404(Order, pk=pk)
        try:
            invoice = approve_order(order, request.user)
            messages.success(request, f"Order approved. Invoice {invoice.invoice_number} created.")
        except Exception as e:
            messages.error(request, str(e))
    return redirect("order_detail", pk=pk)


@login_required
@role_required("admin", "owner")
def order_reject(request, pk):
    if request.method == "POST":
        order = get_object_or_404(Order, pk=pk)
        order.status = "rejected"
        order.save()
        messages.success(request, f"Order #{order.id} rejected.")
    return redirect("order_list")


@login_required
def invoice_list(request):
    invoices = Invoice.objects.select_related("customer").order_by("-invoice_date")
    return render(request, "sales/invoice_list.html", {"invoices": invoices})


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("customer").prefetch_related("lines__item"), pk=pk
    )
    payment_allocations = invoice.payment_allocations.select_related("payment").all()
    return render(request, "sales/invoice_detail.html", {
        "invoice": invoice,
        "payment_allocations": payment_allocations,
        "outstanding_paise": invoice.outstanding_paise,
    })


@login_required
def invoice_pdf(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("customer").prefetch_related("lines__item"), pk=pk
    )
    from services.pdf import render_invoice_pdf
    pdf_bytes = render_invoice_pdf(invoice)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="invoice_{invoice.invoice_number}.pdf"'
    return response


@login_required
def payment_list(request):
    payments = Payment.objects.select_related("customer").order_by("-payment_date")
    return render(request, "sales/payment_list.html", {"payments": payments})


@login_required
@role_required("admin", "accountant", "owner")
def payment_create(request):
    customers = Customer.objects.filter(is_active=True)
    if request.method == "POST":
        from services.sales import record_payment
        try:
            payment = record_payment(request.POST, request.user)
            messages.success(request, f"Payment of ₹{payment.amount_rupees:.2f} recorded.")
            return redirect("payment_list")
        except Exception as e:
            messages.error(request, str(e))
    # Get all customers with outstanding invoices
    invoices = Invoice.objects.filter(status="posted").select_related("customer")
    return render(request, "sales/payment_create.html", {
        "customers": customers, "invoices": invoices
    })


@login_required
def outstanding(request):
    from services.sales import get_outstanding_by_customer
    data = get_outstanding_by_customer()
    return render(request, "sales/outstanding.html", {"data": data})
