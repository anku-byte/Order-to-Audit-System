from django.contrib import admin
from .models import Item, UnitConversion, StockMovement


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "base_unit", "hsn_code", "gst_rate", "reorder_level", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "hsn_code"]


@admin.register(UnitConversion)
class UnitConversionAdmin(admin.ModelAdmin):
    list_display = ["from_unit", "to_unit", "factor", "item"]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ["item", "movement_type", "qty_delta", "unit_cost", "value", "created_at"]
    list_filter = ["movement_type", "item__category"]
    readonly_fields = list.__add__(
        ["item", "movement_type", "qty_delta", "unit_cost", "value",
         "batch_no", "expiry_date", "source_content_type", "source_object_id",
         "created_by", "created_at"], []
    )

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    def has_change_permission(self, request, obj=None): return False
