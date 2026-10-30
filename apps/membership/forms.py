"""Forms for joining the CBO and confirming the verification code."""

from django import forms
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.core.utils import kenyan_phone_to_254

from .models import DropdownOption, Member

WIDGET = forms.TextInput(attrs={"class": "form-control"})


def options_for(field):
    return [
        (option.label, option.label)
        for option in DropdownOption.objects.filter(field=field, active=True).order_by("order", "label")
    ]


class MemberRegisterForm(forms.ModelForm):
    channel = forms.ChoiceField(
        label="Send my code by",
        choices=[("both", "SMS and email"), ("sms", "SMS only"), ("email", "Email only")],
        initial="both",
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Member
        fields = ["full_name", "phone", "email", "gender", "role", "location", "sub_location", "occupation"]
        widgets = {
            "full_name": WIDGET,
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "07XX XXX XXX", "inputmode": "tel"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Kagan Ward"}),
            "sub_location": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Nyang'oma village"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in DropdownOption.Field.choices:
            choices = options_for(field_name)
            self.fields[field_name] = forms.ChoiceField(
                label=field,
                choices=[("", f"Select {field.lower()}")] + choices,
                required=(field_name != "occupation"),
                widget=forms.Select(attrs={"class": "form-select"}),
            )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        existing = Member.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if existing.filter(verified=True).exists():
            raise ValidationError("This email is already registered as a member. Log in or ask the treasurer for help.")
        if User.objects.filter(email__iexact=email).exists() and not existing.exists():
            raise ValidationError(
                "You already have a login account with this email. Please log in first, then register as a member."
            )
        return email

    def clean_phone(self):
        raw = self.cleaned_data.get("phone", "")
        normalised = kenyan_phone_to_254(raw)
        if not normalised:
            raise ValidationError("Use a Kenyan number, e.g. 0712 345 678 or +254712345678.")
        clash = Member.objects.filter(phone=normalised).exclude(pk=self.instance.pk)
        if clash.filter(verified=True).exists():
            raise ValidationError("This phone number is already registered as a member.")
        return normalised

    def clean_full_name(self):
        name = " ".join(self.cleaned_data["full_name"].split())
        if len(name) < 3:
            raise ValidationError("Write the full name as it appears on the national ID.")
        return name


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
