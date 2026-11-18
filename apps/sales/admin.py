from django.contrib import admin
from .models import Customer, Order, OrderLine, Invoice, InvoiceLine, Payment, PriceList, PriceListLine, CreditNote


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 1


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "customer_type", "state_code", "gstin", "is_active"]
    list_filter = ["customer_type", "state_code", "is_active"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "customer", "salesman", "status", "order_date"]
    list_filter = ["status"]
    inlines = [OrderLineInline]


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    readonly_fields = ["taxable_value_paise", "cgst_paise", "sgst_paise", "igst_paise"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["invoice_number", "customer", "invoice_date", "total_paise", "status"]
    list_filter = ["status", "supply_type"]
    inlines = [InvoiceLineInline]
    readonly_fields = ["invoice_number", "created_at"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["customer", "payment_date", "amount_paise", "mode"]
