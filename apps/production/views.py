from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal
from .models import BOM, ProductionRun, ProductionRunLine, ProductionRunOverhead
from apps.core.mixins import role_required


@login_required
@role_required("production", "admin", "owner")
def production_run_list(request):
    runs = ProductionRun.objects.select_related("bom__product").order_by("-run_date")
    return render(request, "production/run_list.html", {"runs": runs})


@login_required
@role_required("production", "admin", "owner")
def bom_list(request):
    boms = BOM.objects.filter(is_active=True).select_related("product").prefetch_related("lines__item")
    return render(request, "production/bom_list.html", {"boms": boms})


@login_required
@role_required("production", "admin", "owner")
def production_run_create(request):
    boms = BOM.objects.filter(is_active=True).select_related("product")
    if request.method == "POST":
        bom_id = request.POST.get("bom")
        run_date = request.POST.get("run_date")
        batch_multiplier = request.POST.get("batch_multiplier", "1")
        bom = get_object_or_404(BOM, id=bom_id)
        run = ProductionRun.objects.create(
            bom=bom, run_date=run_date, batch_multiplier=batch_multiplier,
            status="draft", created_by=request.user,
        )
        # Pre-populate run lines from BOM
        from services.units import to_base_unit
        for bom_line in bom.lines.select_related("item").all():
            qty_base, _ = to_base_unit(
                bom_line.qty_per_batch * Decimal(batch_multiplier),
                bom_line.unit, bom_line.item
            )
            ProductionRunLine.objects.create(
                run=run, bom_line=bom_line,
                planned_qty=qty_base, actual_qty=qty_base,
                unit=bom_line.item.base_unit,
            )
        messages.success(request, f"Production run #{run.id} created.")
        return redirect("production_run_detail", pk=run.pk)
    return render(request, "production/run_create.html", {"boms": boms})


@login_required
@role_required("production", "admin", "owner")
def production_run_detail(request, pk):
    run = get_object_or_404(ProductionRun.objects.select_related("bom__product"), pk=pk)
    lines = run.lines.select_related("bom_line__item").all()
    overheads = run.overheads.all()
    return render(request, "production/run_detail.html", {
        "run": run, "lines": lines, "overheads": overheads,
    })


@login_required
@role_required("production", "admin", "owner")
def production_run_update(request, pk):
    """Update actual quantities, good output, scrap, damaged packaging."""
    run = get_object_or_404(ProductionRun, pk=pk, status__in=["draft", "in_progress"])
    if request.method == "POST":
        run.actual_good_output = Decimal(request.POST.get("actual_good_output", "0"))
        run.actual_scrap_qty = Decimal(request.POST.get("actual_scrap_qty", "0"))
        run.damaged_packaging_qty = Decimal(request.POST.get("damaged_packaging_qty", "0"))
        run.status = "in_progress"
        run.save()
        # Update run lines
        for line in run.lines.select_related("bom_line__item").all():
            key = f"actual_{line.bom_line_id}"
            if key in request.POST:
                line.actual_qty = Decimal(request.POST[key])
                line.save()
        messages.success(request, "Production run updated.")
        return redirect("production_run_detail", pk=pk)
    lines = run.lines.select_related("bom_line__item").all()
    return render(request, "production/run_update.html", {"run": run, "lines": lines})


@login_required
@role_required("production", "admin", "owner")
def production_run_complete(request, pk):
    if request.method == "POST":
        from services.production import complete_production_run
        run = get_object_or_404(ProductionRun, pk=pk)
        try:
            complete_production_run(run, request.user)
            messages.success(request, f"Run #{run.id} completed. Stock updated.")
        except Exception as e:
            messages.error(request, str(e))
    return redirect("production_run_detail", pk=pk)


@login_required
@role_required("production", "admin", "owner")
def add_overhead(request, pk):
    run = get_object_or_404(ProductionRun, pk=pk)
    if request.method == "POST":
        overhead_type = request.POST.get("overhead_type")
        description = request.POST.get("description", "")
        amount_rupees = Decimal(request.POST.get("amount_rupees", "0"))
        amount_paise = int(amount_rupees * 100)
        ProductionRunOverhead.objects.create(
            run=run, overhead_type=overhead_type,
            description=description, amount_paise=amount_paise,
        )
        messages.success(request, "Overhead added.")
    return redirect("production_run_detail", pk=pk)
