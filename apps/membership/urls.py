from django.urls import path

from . import views

app_name = "membership"

urlpatterns = [
    # Public membership sign-up flow
    path("register/", views.register, name="register"),
    path("verify/", views.verify, name="verify"),
    path("verification-pending/", views.pending, name="pending"),
    # Member area
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/location/", views.location, name="location"),
    path("dashboard/email-us/", views.contact_us, name="contact"),
]
