from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import Purchase, Supplier
from apps.core.mixins import role_required
from apps.inventory.models import Item


@login_required
@role_required("production", "admin", "owner")
def purchase_list(request):
    purchases = Purchase.objects.select_related("supplier").order_by("-purchase_date")
    return render(request, "purchasing/purchase_list.html", {"purchases": purchases})


@login_required
@role_required("production", "admin", "owner")
def purchase_create(request):
    suppliers = Supplier.objects.filter(is_active=True)
    items = Item.objects.filter(is_active=True, category__in=["raw", "pkg"])
    if request.method == "POST":
        from services.purchasing import create_purchase
        try:
            purchase = create_purchase(request.POST, request.user)
            messages.success(request, f"Purchase #{purchase.id} created.")
            return redirect("purchase_detail", pk=purchase.pk)
        except Exception as e:
            messages.error(request, str(e))
    return render(request, "purchasing/purchase_create.html", {
        "suppliers": suppliers, "items": items
    })


@login_required
@role_required("production", "admin", "owner")
def purchase_detail(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.select_related("supplier").prefetch_related("lines__item"), pk=pk
    )
    return render(request, "purchasing/purchase_detail.html", {"purchase": purchase})


@login_required
@role_required("production", "admin", "owner")
def purchase_post(request, pk):
    if request.method == "POST":
        from services.purchasing import post_purchase
        purchase = get_object_or_404(Purchase, pk=pk)
        try:
            post_purchase(purchase, request.user)
            messages.success(request, f"Purchase #{purchase.id} posted. Stock updated.")
        except Exception as e:
            messages.error(request, str(e))
    return redirect("purchase_detail", pk=pk)
