from django.urls import path

from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # Members
    path("members/", views.member_list, name="member_list"),
    path("members/<int:pk>/", views.member_detail, name="member_detail"),
    # Announcements & member messages
    path("messages/", views.campaign_list, name="campaign_list"),
    path("messages/new/", views.campaign_create, name="campaign_create"),
    path("messages/inbox/", views.contact_list, name="contact_list"),
    path("messages/inbox/<int:pk>/mark/", views.contact_mark, name="contact_mark"),
    # Events & reports
    path("events/", views.event_list, name="event_list"),
    path("events/new/", views.event_form, name="event_new"),
    path("events/edit/<int:pk>/", views.event_form, name="event_edit"),
    path("events/<int:pk>/delete/", views.event_delete, name="event_delete"),
    path("reports/", views.report_list, name="report_list"),
    path("reports/new/", views.report_create, name="report_new"),
    path("reports/edit/<int:pk>/", views.report_create, name="report_edit"),
    path("reports/<int:pk>/delete/", views.report_delete, name="report_delete"),
    path("reports/photo/<int:pk>/delete/", views.photo_delete, name="photo_delete"),
    # Money
    path("contributions/", views.contribution_list, name="contribution_list"),
    path("contributions/<int:pk>/decide/", views.contribution_decide, name="contribution_decide"),
    # Incidents
    path("incidents/", views.incident_list, name="incident_list"),
    path("incidents/<int:pk>/", views.incident_detail, name="incident_detail"),
    # Site settings
    path("settings/", views.settings_home, name="settings_home"),
    path("settings/site/", views.settings_site, name="settings_site"),
    path("settings/slider/", views.settings_slider, name="settings_slider"),
    path("settings/slider/<int:pk>/delete/", views.slider_delete, name="slider_delete"),
    path("settings/social/", views.settings_social, name="settings_social"),
    path("settings/nav/", views.settings_nav, name="settings_nav"),
    path("settings/nav/<int:pk>/delete/", views.nav_delete, name="nav_delete"),
    path("settings/options/", views.settings_options, name="settings_options"),
    path("settings/options/<int:pk>/delete/", views.option_delete, name="option_delete"),
    # Audit trail
    path("audit/", views.audit_list, name="audit_list"),
]
