from django.contrib import admin
from .models import BOM, BOMLine, ProductionRun, ProductionRunLine, ProductionRunOverhead


class BOMLineInline(admin.TabularInline):
    model = BOMLine
    extra = 1


@admin.register(BOM)
class BOMAdmin(admin.ModelAdmin):
    list_display = ["name", "product", "expected_yield", "is_active"]
    inlines = [BOMLineInline]


class PRLineInline(admin.TabularInline):
    model = ProductionRunLine
    extra = 0
    readonly_fields = ["variance_pct", "is_flagged"]


class PROverheadInline(admin.TabularInline):
    model = ProductionRunOverhead
    extra = 1


@admin.register(ProductionRun)
class ProductionRunAdmin(admin.ModelAdmin):
    list_display = ["id", "bom", "run_date", "status", "planned_output", "actual_good_output"]
    list_filter = ["status"]
    inlines = [PRLineInline, PROverheadInline]
    readonly_fields = ["planned_output", "created_at", "completed_at"]
