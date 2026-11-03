"""Authentication and profile forms.

Registration itself lives in apps.membership.forms.RegisterForm, because an
account and a membership are now created together in one step.
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm as DjangoPasswordChangeForm
from django.contrib.auth.password_validation import get_default_password_validators
from django.core.exceptions import ValidationError

from apps.core.utils import kenyan_phone_to_254

from .models import LoginAttempt, User

INPUT = forms.TextInput(attrs={"class": "form-control"})
PASSWORD = forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"})


def password_help_text():
    return " ".join(v.get_help_text() for v in get_default_password_validators())


class ThrottledAuthenticationForm(AuthenticationForm):
    """Login with email + password only; unverified accounts are refused with a way out."""

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].label = "Email address"
        self.fields["username"].widget = INPUT
        self.fields["password"].widget = forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "current-password"}
        )

    def clean_username(self):
        return (self.cleaned_data.get("username") or "").strip().lower()

    def clean(self):
        email = (self.cleaned_data.get("username") or "").strip().lower()
        locked_for = LoginAttempt.lockout_seconds(email)
        if locked_for:
            minutes = max(1, locked_for // 60 + 1)
            raise forms.ValidationError(
                f"Too many wrong attempts on this account. Wait {minutes} minute(s) and try again, "
                "or use 'Forgot password'."
            )
        user = User.objects.filter(email__iexact=email).first()
        if user is not None and not user.is_active and not user.is_administrator:
            raise forms.ValidationError(
                "This account is not verified yet. Enter the 6-digit code we emailed you, or use "
                "'Resend verification code' below to get a fresh one."
            )
        try:
            cleaned = super().clean()
        except forms.ValidationError:
            LoginAttempt.register_failure(email)
            raise
        LoginAttempt.clear(email)
        return cleaned


class ResendCodeForm(forms.Form):
    """Asks for a fresh verification code for an account that is still inactive."""

    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["name", "email", "phone", "photo"]
        widgets = {
            "name": INPUT,
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "photo": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
        }

    def clean_email(self):
        from apps.membership.models import Member

        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Another account already uses that email address.")
        taken = Member.objects.filter(email__iexact=email).exclude(user=self.instance)
        if taken.exists():
            raise ValidationError("That email address already belongs to another member.")
        return email

    def clean_phone(self):
        raw = self.cleaned_data.get("phone") or ""
        if not raw:
            return ""
        normalised = kenyan_phone_to_254(raw)
        if not normalised:
            raise ValidationError("Use a Kenyan number such as 07XX XXX XXX or +2547XX XXX XXX.")
        return normalised


class AccountPasswordChangeForm(DjangoPasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
