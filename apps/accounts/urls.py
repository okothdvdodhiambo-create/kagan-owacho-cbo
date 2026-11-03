from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.OrganizationLoginView.as_view(), name="login"),
    path("resend-code/", views.resend_code, name="resend_code"),
    path("logout/", views.OrganizationLogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("password/change/", views.password_change, name="password_change"),
    path("password/forgot/", views.ForgotPasswordView.as_view(), name="password_reset"),
    path("password/forgot/sent/", views.ForgotPasswordDoneView.as_view(), name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", views.ForgotPasswordConfirmView.as_view(), name="password_reset_confirm"),
    path("password/reset/complete/", views.ForgotPasswordCompleteView.as_view(), name="password_reset_complete"),
    # The account-only page is gone; this keeps old links and bookmarks alive.
    path("register/", views.old_signup_redirect, name="signup"),
]
