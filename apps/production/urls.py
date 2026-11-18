from django.urls import path
from . import views

urlpatterns = [
    path("", views.production_run_list, name="production_run_list"),
    path("new/", views.production_run_create, name="production_run_create"),
    path("<int:pk>/", views.production_run_detail, name="production_run_detail"),
    path("<int:pk>/update/", views.production_run_update, name="production_run_update"),
    path("<int:pk>/complete/", views.production_run_complete, name="production_run_complete"),
    path("<int:pk>/overhead/add/", views.add_overhead, name="add_overhead"),
    path("bom/", views.bom_list, name="bom_list"),
]
