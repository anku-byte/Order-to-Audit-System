from django.urls import path
from . import views

urlpatterns = [
    path("", views.stock_summary, name="stock_summary"),
    path("ledger/<int:item_id>/", views.stock_ledger, name="stock_ledger"),
    path("items/", views.item_list, name="item_list"),
]
