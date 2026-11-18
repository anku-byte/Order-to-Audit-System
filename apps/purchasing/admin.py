from django.contrib import admin
from .models import Supplier, Purchase, PurchaseLine


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 1


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["name", "gstin", "state_code", "is_active"]


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ["id", "supplier", "purchase_date", "status"]
    list_filter = ["status"]
    inlines = [PurchaseLineInline]
