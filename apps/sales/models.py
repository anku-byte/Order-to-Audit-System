"""
Sales models.

Invoice numbering: INV/26-27/0001 (max 16 chars). Sequence resets each April.
GST: intrastate (customer state == FACTORY_STATE_CODE='TN') → CGST+SGST.
     interstate → IGST. Computed per line, rounded half-up per line.
Posted invoices: NEVER deleted. Cancel via CreditNote.
Money: integer paise throughout.
"""
from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()

INDIAN_STATE_CHOICES = [
    ("AN","Andaman & Nicobar"),("AP","Andhra Pradesh"),("AR","Arunachal Pradesh"),
    ("AS","Assam"),("BR","Bihar"),("CH","Chandigarh"),("CG","Chhattisgarh"),
    ("DD","Daman & Diu"),("DL","Delhi"),("GA","Goa"),("GJ","Gujarat"),
    ("HR","Haryana"),("HP","Himachal Pradesh"),("JK","J & K"),("JH","Jharkhand"),
    ("KA","Karnataka"),("KL","Kerala"),("LA","Ladakh"),("LD","Lakshadweep"),
    ("MP","Madhya Pradesh"),("MH","Maharashtra"),("MN","Manipur"),("ML","Meghalaya"),
    ("MZ","Mizoram"),("NL","Nagaland"),("OD","Odisha"),("PY","Puducherry"),
    ("PB","Punjab"),("RJ","Rajasthan"),("SK","Sikkim"),("TN","Tamil Nadu"),
    ("TS","Telangana"),("TR","Tripura"),("UP","Uttar Pradesh"),
    ("UK","Uttarakhand"),("WB","West Bengal"),
]


class CustomerType(models.TextChoices):
    RETAILER = "retailer", "Retailer"
    DISTRIBUTOR = "distributor", "Distributor"
    DIRECT = "direct", "Direct Customer"


class Customer(models.Model):
    name = models.CharField(max_length=200)
    customer_type = models.CharField(max_length=20, choices=CustomerType.choices)
    gstin = models.CharField(max_length=15, blank=True)
    state_code = models.CharField(max_length=2, choices=INDIAN_STATE_CHOICES, default="TN")
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_customer_type_display()}, {self.state_code})"

    @property
    def is_intrastate(self):
        return self.state_code == getattr(settings, "FACTORY_STATE_CODE", "TN")

    @property
    def supply_type(self):
        return "intrastate" if self.is_intrastate else "interstate"


class PriceList(models.Model):
    name = models.CharField(max_length=100)
    effective_from = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PriceListLine(models.Model):
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("inventory.Item", on_delete=models.PROTECT,
                              limit_choices_to={"category": "fg"})
    unit_price_paise = models.PositiveIntegerField()

    class Meta:
        unique_together = [("price_list", "item")]

    @property
    def unit_price_rupees(self):
        return Decimal(self.unit_price_paise) / 100


class CustomerPriceOverride(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="price_overrides")
    item = models.ForeignKey("inventory.Item", on_delete=models.PROTECT,
                              limit_choices_to={"category": "fg"})
    unit_price_paise = models.PositiveIntegerField()
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)


class OrderStatus(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    INVOICED = "invoiced", "Invoiced"
    DISPATCHED = "dispatched", "Dispatched"


class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    salesman = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders")
    order_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.SUBMITTED)
    notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="approved_orders")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.id} – {self.customer.name} [{self.status}]"


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("inventory.Item", on_delete=models.PROTECT,
                              limit_choices_to={"category": "fg"})
    qty = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price_paise = models.PositiveIntegerField()
    notes = models.TextField(blank=True)

    @property
    def line_total_paise(self):
        return int(self.qty * self.unit_price_paise)


def _current_fy() -> str:
    from datetime import date
    today = date.today()
    if today.month >= 4:
        return f"{str(today.year)[2:]}-{str(today.year+1)[2:]}"
    return f"{str(today.year-1)[2:]}-{str(today.year)[2:]}"


def _next_invoice_number(fy: str) -> str:
    """INV/26-27/0001 format, max 16 chars. Sequence resets each April."""
    prefix = f"INV/{fy}/"
    last = (
        Invoice.objects.filter(invoice_number__startswith=prefix)
        .order_by("-invoice_number")
        .values_list("invoice_number", flat=True)
        .first()
    )
    seq = int(last[-4:]) + 1 if last else 1
    return f"{prefix}{seq:04d}"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        CANCELLED = "cancelled", "Cancelled"

    order = models.OneToOneField(Order, null=True, blank=True, on_delete=models.PROTECT,
                                  related_name="invoice")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="invoices")
    invoice_number = models.CharField(max_length=16, unique=True, blank=True)
    invoice_date = models.DateField()
    fy = models.CharField(max_length=5)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    supply_type = models.CharField(max_length=20,
                                    choices=[("intrastate","Intrastate"),("interstate","Interstate")])
    taxable_value_paise = models.PositiveIntegerField(default=0)
    cgst_paise = models.PositiveIntegerField(default=0)
    sgst_paise = models.PositiveIntegerField(default=0)
    igst_paise = models.PositiveIntegerField(default=0)
    total_paise = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-invoice_date", "-invoice_number"]

    def __str__(self):
        return f"{self.invoice_number} – {self.customer.name}"

    @property
    def total_rupees(self):
        return Decimal(self.total_paise) / 100

    @property
    def outstanding_paise(self):
        allocated = sum(a.allocated_paise for a in self.payment_allocations.all())
        return self.total_paise - allocated

    def post(self):
        if self.status != self.Status.DRAFT:
            raise ValueError("Only draft invoices can be posted.")
        if not self.fy:
            self.fy = _current_fy()
        if not self.invoice_number:
            self.invoice_number = _next_invoice_number(self.fy)
        self.status = self.Status.POSTED
        self.save()


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("inventory.Item", on_delete=models.PROTECT)
    hsn_code = models.CharField(max_length=20)
    qty = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price_paise = models.PositiveIntegerField()
    taxable_value_paise = models.PositiveIntegerField(default=0)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2)
    cgst_paise = models.PositiveIntegerField(default=0)
    sgst_paise = models.PositiveIntegerField(default=0)
    igst_paise = models.PositiveIntegerField(default=0)

    @property
    def line_total_paise(self):
        return self.taxable_value_paise + self.cgst_paise + self.sgst_paise + self.igst_paise


class CreditNote(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="credit_notes")
    cn_number = models.CharField(max_length=16, unique=True)
    cn_date = models.DateField()
    reason = models.TextField()
    amount_paise = models.PositiveIntegerField()
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.cn_number} against {self.invoice.invoice_number}"


class Dispatch(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="dispatches")
    dispatch_date = models.DateField()
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class DispatchLine(models.Model):
    dispatch = models.ForeignKey(Dispatch, on_delete=models.CASCADE, related_name="lines")
    invoice_line = models.ForeignKey(InvoiceLine, on_delete=models.PROTECT)
    qty_dispatched = models.DecimalField(max_digits=14, decimal_places=3)


class PaymentMode(models.TextChoices):
    CASH = "cash", "Cash"
    CHEQUE = "cheque", "Cheque"
    UPI = "upi", "UPI"
    NEFT = "neft", "NEFT / RTGS"
    OTHER = "other", "Other"


class Payment(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="payments")
    payment_date = models.DateField()
    amount_paise = models.PositiveIntegerField()
    mode = models.CharField(max_length=10, choices=PaymentMode.choices)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def amount_rupees(self):
        return Decimal(self.amount_paise) / 100

    def __str__(self):
        return f"₹{self.amount_rupees:.2f} from {self.customer.name} on {self.payment_date}"


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="allocations")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payment_allocations")
    allocated_paise = models.PositiveIntegerField()

    class Meta:
        unique_together = [("payment", "invoice")]
