"""Forms for joining the CBO and confirming the verification code.

One form collects the account *and* the membership details, because having an
account now means being a member - there is no separate sign-up any more.
"""

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.accounts.forms import password_help_text
from apps.accounts.models import User
from apps.core.utils import kenyan_phone_to_254, validate_image_file

from .models import DropdownOption, Member

WIDGET = forms.TextInput(attrs={"class": "form-control"})
INPUT = forms.TextInput(attrs={"class": "form-control"})
PASSWORD = forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"})


def options_for(field):
    return [
        (option.label, option.label)
        for option in DropdownOption.objects.filter(field=field, active=True).order_by("order", "label")
    ]


def dropdown_choices(field_name, label, current=""):
    """Admin-editable options, keeping a value that has since been withdrawn selectable."""
    choices = options_for(field_name)
    if current and current not in [value for value, _label in choices]:
        choices = [(current, f"{current} (old option)")] + choices
    return [("", f"Select {label.lower()}")] + choices


def normalised_phone(raw):
    if not raw:
        return ""
    phone = kenyan_phone_to_254(raw)
    if not phone:
        raise ValidationError("Use a Kenyan number, e.g. 0712 345 678 or +254712345678.")
    return phone


class MemberFieldsMixin:
    """The membership half of the form: phone plus the admin-editable dropdowns."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"] = forms.CharField(
            label="Phone number",
            max_length=20,
            widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "07XX XXX XXX", "inputmode": "tel"}),
        )
        for field_name, field_label in DropdownOption.Field.choices:
            self.fields[field_name] = forms.ChoiceField(
                label=field_label,
                choices=dropdown_choices(field_name, field_label),
                required=(field_name != "occupation"),
                widget=forms.Select(attrs={"class": "form-select"}),
            )
        self.fields["location"] = forms.CharField(
            max_length=120, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Kagan Ward"})
        )
        self.fields["sub_location"] = forms.CharField(
            label="Sub-location",
            required=False,
            max_length=120,
            widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Nyang'oma village"}),
        )
        # These fields are added after BaseForm.__init__ ordered them, so re-apply.
        if getattr(self, "field_order", None):
            self.order_fields(self.field_order)

    def member_details(self):
        """The cleaned values that belong on the Member row."""
        return {
            "phone": self.cleaned_data["phone"],
            "gender": self.cleaned_data.get("gender", ""),
            "role": self.cleaned_data.get("role", ""),
            "location": self.cleaned_data["location"],
            "sub_location": self.cleaned_data.get("sub_location", ""),
            "occupation": self.cleaned_data.get("occupation", ""),
        }


class RegisterForm(MemberFieldsMixin, forms.Form):
    """Create the login account and the membership record in one step."""

    name = forms.CharField(label="Full name (as on the national ID)", max_length=150, widget=INPUT)
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    password1 = forms.CharField(label="Password", strip=False, widget=PASSWORD, help_text=password_help_text())
    password2 = forms.CharField(label="Confirm password", strip=False, widget=PASSWORD)
    photo = forms.ImageField(
        label="Profile photo",
        required=False,
        validators=[validate_image_file],
        widget=forms.FileInput(attrs={"class": "form-control", "accept": "image/*"}),
    )

    field_order = [
        "name", "email", "phone", "password1", "password2",
        "gender", "role", "location", "sub_location", "occupation", "photo",
    ]

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if len(name) < 3:
            raise ValidationError("Write the full name as it appears on the national ID.")
        return name

    def pending_account(self):
        """An existing account that was never verified, if this email matches one."""
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            return None
        user = User.objects.filter(email__iexact=email).first()
        if user is None or user.is_active or user.is_administrator:
            return None
        return user

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        existing = User.objects.filter(email__iexact=email).first()
        if existing is not None and not (existing.is_administrator or existing.is_active):
            # Registered but never verified: the same person may try again with corrections.
            return email
        if existing is not None:
            raise ValidationError(
                "That email address is already registered. Log in, or use 'Forgot password' if you need a new one."
            )
        if Member.objects.filter(email__iexact=email, verified=True).exists():
            raise ValidationError("This email is already registered as a member. Log in or ask the treasurer for help.")
        return email

    def clean_phone(self):
        phone = normalised_phone(self.cleaned_data.get("phone"))
        email = (self.cleaned_data.get("email") or "").strip().lower()
        clash = Member.objects.filter(phone=phone).exclude(email__iexact=email)
        if clash.filter(verified=True).exists():
            raise ValidationError("This phone number is already registered as a member.")
        if clash.exists():
            raise ValidationError("Another registration waiting for verification already uses this phone number.")
        return phone

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        if password and cleaned.get("password2") != password:
            self.add_error("password2", "The two passwords do not match.")
        if password:
            draft = User(name=cleaned.get("name", ""), email=cleaned.get("email", ""), phone=cleaned.get("phone", ""))
            try:
                validate_password(password, draft)
            except ValidationError as exc:
                self.add_error("password1", exc.messages)
        return cleaned

    def member_details(self):
        details = super().member_details()
        details["full_name"] = self.cleaned_data["name"]
        details["email"] = self.cleaned_data["email"]
        return details


class CompleteMembershipForm(MemberFieldsMixin, forms.Form):
    """Member details for an account that was created before the two steps merged.

    The email stays as it is on the account, so this form only collects the
    membership fields.
    """

    def __init__(self, *args, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member
        if member is None:
            return
        for field_name, field_label in DropdownOption.Field.choices:
            current = getattr(member, field_name, "")
            if current:
                self.initial.setdefault(field_name, current)
                self.fields[field_name].choices = dropdown_choices(field_name, field_label, current)
        for field_name in ("phone", "location"):
            if getattr(member, field_name, ""):
                self.initial.setdefault(field_name, getattr(member, field_name))

    def clean_phone(self):
        phone = normalised_phone(self.cleaned_data.get("phone"))
        clash = Member.objects.filter(phone=phone).exclude(pk=self.member.pk if self.member else None)
        if clash.filter(verified=True).exists():
            raise ValidationError("This phone number is already registered as a member.")
        return phone

    def member_details(self):
        details = super().member_details()
        details["full_name"] = ""
        return details


class MemberProfileForm(forms.ModelForm):
    """The membership half of the profile page; dropdowns stay admin-controlled."""

    class Meta:
        model = Member
        fields = ["phone", "gender", "role", "location", "sub_location", "occupation"]
        widgets = {
            "phone": forms.TextInput(attrs={"class": "form-control", "inputmode": "tel"}),
            "location": WIDGET,
            "sub_location": WIDGET,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field_label in DropdownOption.Field.choices:
            current = getattr(self.instance, field_name, "") if self.instance.pk else ""
            self.fields[field_name] = forms.ChoiceField(
                label=field_label,
                choices=dropdown_choices(field_name, field_label, current),
                required=(field_name != "occupation"),
                widget=forms.Select(attrs={"class": "form-select"}),
            )
        self.fields["occupation"].required = False
        self.fields["sub_location"].required = False

    def clean_phone(self):
        return normalised_phone(self.cleaned_data.get("phone"))


class VerificationCodeForm(forms.Form):
    code = forms.CharField(
        label="6-digit code",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={"class": "form-control form-control-lg text-center code-input", "inputmode": "numeric", "autocomplete": "one-time-code", "placeholder": "------"}
        ),
    )

    def clean_code(self):
        raw = self.cleaned_data["code"].strip()
        if not raw.isdigit() or len(raw) != 6:
            raise ValidationError("Enter the 6 digits exactly as they were sent to you.")
        return raw


class MemberDetailsForm(forms.ModelForm):
    """Used by the admin when correcting a member's record."""

    class Meta:
        model = Member
        fields = ["full_name", "phone", "email", "gender", "role", "location", "sub_location", "occupation", "status"]
        widgets = {
            "full_name": WIDGET,
            "phone": WIDGET,
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "location": WIDGET,
            "sub_location": WIDGET,
            "occupation": WIDGET,
            "gender": WIDGET,
            "role": WIDGET,
            "status": forms.Select(attrs={"class": "form-select"}),
        }
