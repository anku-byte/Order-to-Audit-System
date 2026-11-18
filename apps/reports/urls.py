from django.urls import path
from . import views

urlpatterns = [
    path("", views.reports_home, name="reports_home"),
    path("sales/", views.sales_register, name="report_sales"),
    path("gst/", views.gst_summary, name="report_gst"),
    path("stock/", views.stock_report, name="report_stock"),
    path("production/", views.production_report, name="report_production"),
    path("outstanding/", views.outstanding_report, name="report_outstanding"),
    path("purchases/", views.purchase_report, name="report_purchases"),
]
