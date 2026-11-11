"""Log in/out, profile, verification resend and password pages."""

from django.conf import settings
from django.contrib import messages
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

from apps.core.models import AuditLog
from apps.membership import services as membership_services
from apps.membership.forms import MemberProfileForm
from apps.membership.models import Member

from .forms import AccountPasswordChangeForm, ProfileForm, ResendCodeForm, ThrottledAuthenticationForm


class OrganizationLoginView(LoginView):
    """Email + password only. Admins go to the admin dashboard; members must have a record."""

    template_name = "accounts/login.html"
    authentication_form = ThrottledAuthenticationForm
    redirect_authenticated_user = True
    extra_context = {"page_title": "Log in"}

    def get_success_url(self):
        user = self.request.user
        if user.is_administrator:
            return reverse_lazy("admin_panel:dashboard")
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to
        if user.membership is None:
            return reverse_lazy("membership:complete")
        return reverse_lazy("core:home")


class OrganizationLogoutView(DjangoLogoutView):
    next_page = "core:home"


def old_signup_redirect(request):
    """Account-only sign-up is gone: /accounts/register/ now leads to the combined form."""
    return redirect("membership:register")


def resend_code(request):
    """Send a fresh 6-digit code to an account that is still waiting for verification."""
    form = ResendCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        member = Member.objects.filter(email__iexact=email, verified=False).order_by("-created_at").first()
        if member is None:
            # Deliberately vague: never confirm which addresses are registered.
            messages.success(
                request,
                "If that email belongs to a registration waiting for verification, a new code is on its way.",
            )
        else:
            allowed, seconds = member.can_resend_code
            if not allowed:
                messages.error(request, f"Please wait {seconds} seconds before requesting another code.")
            else:
                _code, plaintext, report = membership_services.issue_code(member)
                if membership_services.email_not_configured():
                    messages.error(request, membership_services.EMAIL_NOT_CONFIGURED)
                elif membership_services.email_failed(report):
                    messages.error(
                        request,
                        "We could not send the email just now. Please try again shortly or contact the treasurer.",
                    )
                else:
                    messages.success(request, "A new 6-digit code is on its way to " + email + ".")
                if settings.DEBUG:
                    messages.warning(request, f"Development mode - the code is {plaintext}.")
        return redirect("accounts:resend_code")
    return render(
        request,
        "accounts/resend_code.html",
        {"form": form, "page_title": "Resend verification code"},
    )


@login_required
def profile(request):
    """Edit the account and the membership details on one page."""
    user = request.user
    member = Member.objects.filter(user=user).order_by("-created_at").first()
    account_form = ProfileForm(request.POST or None, request.FILES or None, instance=user)
    member_form = MemberProfileForm(request.POST or None, instance=member) if member is not None else None
    if member_form is not None:
        # The phone number lives on the membership row when there is one.
        account_form.fields.pop("phone", None)

    if request.method == "POST" and account_form.is_valid() and (member_form is None or member_form.is_valid()):
        saved_user = account_form.save()
        if member_form is not None:
            # ProfileForm.clean_email already refuses an address another member holds.
            member_form.instance.email = saved_user.email
            updated_member = member_form.save()
            if saved_user.phone != updated_member.phone:
                saved_user.phone = updated_member.phone
                saved_user.save(update_fields=["phone"])
        AuditLog.record(saved_user, "profile.updated", target=saved_user.email, request=request)
        messages.success(request, "Profile updated.")
        return redirect("accounts:profile")

    return render(
        request,
        "accounts/profile.html",
        {
            "form": account_form,
            "account_form": account_form,
            "member_form": member_form,
            "member": member,
            "page_title": "Edit profile",
        },
    )


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
