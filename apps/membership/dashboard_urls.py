"""Member dashboard URLs (mounted at /dashboard/)."""

from django.urls import path

from . import views

app_name = "membership"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("location/", views.location, name="location"),
    path("email-us/", views.contact_us, name="contact"),
]
