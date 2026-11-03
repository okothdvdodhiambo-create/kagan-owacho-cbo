from django.urls import path

from . import views

app_name = "membership"

urlpatterns = [
    # Public registration flow: one form, then the emailed code
    path("register/", views.register, name="register"),
    path("verify/", views.verify, name="verify"),
    path("complete/", views.complete, name="complete"),
    path("verification-pending/", views.pending, name="pending"),
    # Member area
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/location/", views.location, name="location"),
    path("dashboard/email-us/", views.contact_us, name="contact"),
]
