from django.urls import path

from . import views

app_name = "contributions"

urlpatterns = [
    path("", views.choose_method, name="choose"),
    path("mpesa/", views.mpesa_stk, name="mpesa"),
    path("mpesa/callback/", views.mpesa_callback, name="mpesa_callback"),
    path("mpesa/record-code/", views.mpesa_manual, name="manual"),
    path("mpesa/<int:pk>/waiting/", views.waiting, name="waiting"),
    path("mpesa/<int:pk>/status/", views.waiting_status, name="waiting_status"),
    path("bank/", views.bank, name="bank"),
    path("transcript/", views.transcript, name="transcript"),
    path("statement/", views.statement, name="statement"),
]
