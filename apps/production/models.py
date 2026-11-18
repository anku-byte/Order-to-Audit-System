"""
Production models: BOM and ProductionRun.

Variance rule:
  variance_pct = (actual - planned) / planned * 100
  Flagged if abs(variance_pct) > VARIANCE_TOLERANCE_PCT (default 3).
  EXCLUSIVE: exactly 3% does NOT flag. Benchmark: -6% and +5% are both flagged.

Cost per packet = (material cost issued + overheads) / good_output.
Material cost: sum of |value| from production_issue StockMovement rows for this run.
Overheads: sum of ProductionRunOverhead.amount_paise.
"""
from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()


class BOM(models.Model):
    product = models.ForeignKey(
        "inventory.Item", on_delete=models.PROTECT, related_name="boms",
        limit_choices_to={"category": "fg"},
    )
    name = models.CharField(max_length=200)
    expected_yield = models.DecimalField(max_digits=14, decimal_places=3,
                                          help_text="Expected FG units per one standard batch")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "BOM"

    def __str__(self):
        return f"{self.name} (yield: {self.expected_yield})"


class BOMLine(models.Model):
    bom = models.ForeignKey(BOM, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(
        "inventory.Item", on_delete=models.PROTECT,
        limit_choices_to={"category__in": ["raw", "pkg"]},
    )
    qty_per_batch = models.DecimalField(max_digits=14, decimal_places=3)
    unit = models.CharField(max_length=20)

    class Meta:
        unique_together = [("bom", "item")]

    def __str__(self):
        return f"{self.bom.product.name}: {self.qty_per_batch} {self.unit} {self.item.name}"


class RunStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class ProductionRun(models.Model):
    """
    One production batch. batch_multiplier scales the BOM (1.0 = 1 standard batch).
    On completion, services/production.py creates StockMovement rows.
    """
    bom = models.ForeignKey(BOM, on_delete=models.PROTECT, related_name="runs")
    run_date = models.DateField()
    batch_multiplier = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("1.000"))
    status = models.CharField(max_length=20, choices=RunStatus.choices, default=RunStatus.DRAFT)
    planned_output = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    actual_good_output = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    actual_scrap_qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    damaged_packaging_qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"),
                                                 help_text="Pouches/packaging damaged during run")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, related_name="production_runs")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-run_date", "-created_at"]

    def __str__(self):
        return f"Run #{self.id} – {self.bom.product.name} on {self.run_date} [{self.status}]"

    def save(self, *args, **kwargs):
        self.planned_output = self.bom.expected_yield * self.batch_multiplier
        super().save(*args, **kwargs)

    @property
    def yield_variance_pct(self):
        if not self.planned_output:
            return Decimal("0")
        return ((self.actual_good_output - self.planned_output) / self.planned_output * 100
                ).quantize(Decimal("0.01"))

    @property
    def yield_variance_flagged(self):
        tol = getattr(settings, "VARIANCE_TOLERANCE_PCT", 3)
        return abs(self.yield_variance_pct) > tol

    @property
    def cost_per_packet_paise(self):
        if not self.actual_good_output:
            return 0
        from django.contrib.contenttypes.models import ContentType
        from apps.inventory.models import StockMovement
        ct = ContentType.objects.get_for_model(self)
        material_value = abs(sum(
            m.value for m in StockMovement.objects.filter(
                source_content_type=ct,
                source_object_id=self.id,
                movement_type="production_issue",
            )
        ))
        overhead = sum(o.amount_paise for o in self.overheads.all())
        total = material_value + overhead
        return int(Decimal(total) / self.actual_good_output)

    @property
    def cost_per_packet_rupees(self):
        return Decimal(self.cost_per_packet_paise) / 100


class ProductionRunLine(models.Model):
    """Planned vs actual per-ingredient line. Stored in item's BASE unit."""
    run = models.ForeignKey(ProductionRun, on_delete=models.CASCADE, related_name="lines")
    bom_line = models.ForeignKey(BOMLine, on_delete=models.PROTECT)
    planned_qty = models.DecimalField(max_digits=14, decimal_places=3)
    actual_qty = models.DecimalField(max_digits=14, decimal_places=3)
    unit = models.CharField(max_length=20)
    variance_pct = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0"))
    is_flagged = models.BooleanField(default=False)

    class Meta:
        unique_together = [("run", "bom_line")]

    def save(self, *args, **kwargs):
        if self.planned_qty:
            self.variance_pct = (
                (self.actual_qty - self.planned_qty) / self.planned_qty * 100
            ).quantize(Decimal("0.0001"))
            tol = getattr(settings, "VARIANCE_TOLERANCE_PCT", 3)
            self.is_flagged = abs(self.variance_pct) > tol
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Run#{self.run_id} {self.bom_line.item.name}: planned={self.planned_qty} actual={self.actual_qty}"


class OverheadType(models.TextChoices):
    LABOUR = "labour", "Labour"
    POWER = "power", "Power / Electricity"
    GAS = "gas", "Gas / Fuel"
    OTHER = "other", "Other"


class ProductionRunOverhead(models.Model):
    run = models.ForeignKey(ProductionRun, on_delete=models.CASCADE, related_name="overheads")
    overhead_type = models.CharField(max_length=20, choices=OverheadType.choices)
    description = models.CharField(max_length=200, blank=True)
    amount_paise = models.PositiveIntegerField()

    @property
    def amount_rupees(self):
        return Decimal(self.amount_paise) / 100

    def __str__(self):
        return f"{self.overhead_type} ₹{self.amount_rupees:.2f} for Run#{self.run_id}"
