from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="list"),
    path("calendar/", views.calendar, name="calendar"),
    path("feed/", views.event_feed, name="feed"),
    path("<int:pk>/", views.event_detail, name="detail"),
    path("reports/<int:pk>/", views.report_detail, name="report_detail"),
]
