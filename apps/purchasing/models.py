from django.db import models
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()


class Supplier(models.Model):
    name = models.CharField(max_length=200)
    gstin = models.CharField(max_length=15, blank=True)
    state_code = models.CharField(max_length=2, default="TN")
    address = models.TextField(blank=True)
    contact = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Purchase(models.Model):
    """Purchase / GRN. On posting, creates StockMovement rows and updates WAC."""
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    purchase_date = models.DateField()
    invoice_ref = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-purchase_date", "-created_at"]

    def __str__(self):
        return f"Purchase #{self.id} from {self.supplier.name} on {self.purchase_date}"

    @property
    def total_paise(self):
        return sum(line.total_paise for line in self.lines.all())


class PurchaseLine(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("inventory.Item", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=14, decimal_places=3)
    unit = models.CharField(max_length=20)
    unit_price_paise = models.PositiveIntegerField()
    qty_in_base = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    total_paise = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.item.name}: {self.qty} {self.unit}"
