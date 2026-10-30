"""Authentication, registration and profile forms."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm as DjangoPasswordChangeForm
from django.contrib.auth.password_validation import get_default_password_validators
from django.core.exceptions import ValidationError

from apps.core.utils import kenyan_phone_to_254, validate_image_file

from .models import LoginAttempt, User

INPUT = forms.TextInput(attrs={"class": "form-control"})
PASSWORD = forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"})


def password_help_text():
    return " ".join(v.get_help_text() for v in get_default_password_validators())


class ThrottledAuthenticationForm(AuthenticationForm):
    """Login with email + password only; blocks after repeated wrong attempts."""

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
        try:
            cleaned = super().clean()
        except forms.ValidationError:
            LoginAttempt.register_failure(email)
            raise
        LoginAttempt.clear(email)
        return cleaned


class SignupForm(forms.Form):
    name = forms.CharField(max_length=150, widget=INPUT)
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    phone = forms.CharField(
        required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "+2547XXXXXXXX"})
    )
    password1 = forms.CharField(label="Password", strip=False, widget=PASSWORD, help_text=password_help_text())
    password2 = forms.CharField(label="Confirm password", strip=False, widget=PASSWORD)
    photo = forms.ImageField(
        required=False,
        validators=[validate_image_file],
        widget=forms.FileInput(attrs={"class": "form-control", "accept": "image/*"}),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("That email address already has an account. Try logging in instead.")
        return email

    def clean_phone(self):
        raw = self.cleaned_data.get("phone") or ""
        if not raw:
            return ""
        normalised = kenyan_phone_to_254(raw)
        if not normalised:
            raise ValidationError("Use a Kenyan number such as 07XX XXX XXX or +2547XX XXX XXX.")
        return normalised

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        if password and cleaned.get("password2") != password:
            self.add_error("password2", "The two passwords do not match.")
        if password:
            draft = User(name=cleaned.get("name", ""), email=cleaned.get("email", ""))
            try:
                _validate_password(password, draft)
            except ValidationError as exc:
                self.add_error("password1", exc.messages)
        return cleaned

    def create_user(self):
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            name=self.cleaned_data["name"].strip(),
            password=self.cleaned_data["password1"],
            phone=self.cleaned_data.get("phone", ""),
            photo=self.cleaned_data.get("photo"),
        )


def _validate_password(password, user):
    for validator in get_default_password_validators():
        validator.validate(password, user)


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
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Another account already uses that email address.")
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
