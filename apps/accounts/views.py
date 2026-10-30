"""Sign up, log in/out, profile and password pages."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    LogoutView as DjangoLogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import UpdateView

from apps.core.models import AuditLog

from .forms import AccountPasswordChangeForm, ProfileForm, SignupForm, ThrottledAuthenticationForm


class OrganizationLoginView(LoginView):
    """Email + password only; admins land on the admin dashboard, everyone else on Home."""

    template_name = "accounts/login.html"
    authentication_form = ThrottledAuthenticationForm
    redirect_authenticated_user = True
    extra_context = {"page_title": "Log in"}

    def get_success_url(self):
        if self.request.user.is_administrator:
            return reverse_lazy("admin_panel:dashboard")
        return self.get_redirect_url() or reverse_lazy("core:home")


class OrganizationLogoutView(DjangoLogoutView):
    next_page = "core:home"


def signup(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    form = SignupForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        user = form.create_user()
        AuditLog.record(user, "account.created", target=user.email, request=request)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(
            request,
            f"Welcome, {user.get_short_name()}! Your account is ready.",
        )
        if user.membership is None:
            return redirect("membership:register")
        return redirect("membership:dashboard")
    return render(request, "accounts/signup.html", {"form": form, "page_title": "Create an account"})


@method_decorator(login_required, name="dispatch")
class ProfileView(UpdateView):
    """Edit name, contact details and profile photo."""

    template_name = "accounts/profile.html"
    form_class = ProfileForm
    success_url = reverse_lazy("accounts:profile")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Profile updated.")
        AuditLog.record(self.request.user, "profile.updated", target=self.object.email, request=self.request)
        return response


@login_required
def password_change(request):
    form = AccountPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        AuditLog.record(request.user, "password.changed", target=request.user.email, request=request)
        messages.success(request, "Your password has been changed.")
        return redirect("membership:dashboard")
    return render(request, "accounts/password_change.html", {"form": form, "page_title": "Change password"})


class ForgotPasswordView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "emails/password_reset.txt"
    subject_template_name = "emails/password_reset_subject.txt"
    html_email_template_name = None
    success_url = reverse_lazy("accounts:password_reset_done")
    extra_context = {"page_title": "Forgot password"}


class ForgotPasswordDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"
    extra_context = {"page_title": "Check your email"}


class ForgotPasswordConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")
    extra_context = {"page_title": "Choose a new password"}


class ForgotPasswordCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
    extra_context = {"page_title": "Password changed"}
