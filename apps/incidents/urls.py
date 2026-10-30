from django.urls import path

from . import views

app_name = "incidents"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("new/", views.report_new, name="new"),
    path("<int:pk>/", views.report_detail, name="detail"),
]
