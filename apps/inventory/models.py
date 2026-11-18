"""
Inventory models.

Stock Design:
- Balances are NEVER stored. Balance = SUM(qty_delta) on StockMovement.
- All money stored as integer paise (100 paise = ₹1). Never float.
- Quantities: Decimal(14,3) in item's BASE unit.
- StockMovement rows are IMMUTABLE; corrections are reversing entries.
- Costing: Weighted Average Cost — smooths price fluctuations, IndAS-2 compliant.
"""
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()


class ItemCategory(models.TextChoices):
    RAW_MATERIAL = "raw", "Raw Material"
    PACKAGING = "pkg", "Packaging"
    FINISHED_GOOD = "fg", "Finished Good"
    WIP = "wip", "Work in Progress"


class Item(models.Model):
    """
    Single item tracked in inventory.
    base_unit is the canonical storage unit; all StockMovement.qty_delta is in this unit.
    HSN code and GST rate sit here so each SKU can differ.
    """
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=10, choices=ItemCategory.choices)
    hsn_code = models.CharField(max_length=20, blank=True)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    base_unit = models.CharField(max_length=20)
    reorder_level = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class UnitConversion(models.Model):
    """
    Conversion factor between units.
    factor: how many to_units make 1 from_unit.
    Example: from_unit='kg', to_unit='g', factor=1000.
    item: if set, applies only to that item (e.g. 1 carton = 20 packets for Murukku).
    """
    from_unit = models.CharField(max_length=20)
    to_unit = models.CharField(max_length=20)
    factor = models.DecimalField(max_digits=20, decimal_places=6)
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        unique_together = [("from_unit", "to_unit", "item")]

    def __str__(self):
        scope = f" [{self.item}]" if self.item else " [global]"
        return f"1 {self.from_unit} = {self.factor} {self.to_unit}{scope}"


class MovementType(models.TextChoices):
    OPENING = "opening", "Opening Balance"
    PURCHASE = "purchase", "Purchase Receipt"
    PRODUCTION_ISSUE = "production_issue", "Production Issue"
    PRODUCTION_OUTPUT = "production_output", "Production Output"
    SCRAP = "scrap", "Scrap"
    SALE_DISPATCH = "sale_dispatch", "Sale Dispatch"
    RETURN = "return", "Return"
    ADJUSTMENT = "adjustment", "Adjustment"
    DAMAGED = "damaged", "Damaged Packaging"


class StockMovement(models.Model):
    """
    APPEND-ONLY stock ledger. Every stock change = one row.
    Balance = SUM(qty_delta). Corrections = new reversing row.

    unit_cost: integer paise per base unit (WAC at time of movement).
    value: integer paise = qty_delta * unit_cost (negative for outgoing).
    qty_delta: Decimal(14,3), NEGATIVE for outgoing.
    """
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=30, choices=MovementType.choices)
    qty_delta = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.PositiveIntegerField(help_text="Paise per base unit")
    value = models.IntegerField(help_text="Total paise; negative for outgoing")
    batch_no = models.CharField(max_length=50, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    source_content_type = models.ForeignKey(ContentType, null=True, blank=True,
                                             on_delete=models.SET_NULL)
    source_object_id = models.PositiveIntegerField(null=True, blank=True)
    source_document = GenericForeignKey("source_content_type", "source_object_id")

    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["item", "created_at"]),
            models.Index(fields=["movement_type"]),
            models.Index(fields=["source_content_type", "source_object_id"]),
        ]

    def __str__(self):
        sign = "+" if self.qty_delta >= 0 else ""
        return f"{self.item.name}: {sign}{self.qty_delta} [{self.movement_type}]"

    @property
    def value_rupees(self):
        return Decimal(self.value) / 100
