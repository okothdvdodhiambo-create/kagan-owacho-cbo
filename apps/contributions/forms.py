"""Amount, phone, reference and receipt forms members fill in."""

from django import forms
from django.core.exceptions import ValidationError

from apps.core.utils import kenyan_phone_to_254, validate_image_file

AMOUNT = forms.DecimalField(
    min_value=10,
    max_value=2000000,
    decimal_places=2,
    max_digits=12,
    widget=forms.NumberInput(
        attrs={
            "class": "form-control",
            "step": "1",
            "min": "10",
            "placeholder": "e.g. 500",
            "data-ksh": "amount",
        }
    ),
    help_text="Minimum KSh 10.",
)
PHONE = forms.CharField(
    widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "07XX XXX XXX", "inputmode": "tel"})
)
DATE = forms.DateInput(attrs={"class": "form-control", "type": "date"})


class MpesaStkForm(forms.Form):
    amount = AMOUNT
    phone = PHONE

    def clean_phone(self):
        normalised = kenyan_phone_to_254(self.cleaned_data["phone"])
        if not normalised:
            raise ValidationError("Enter the Safaricom number that will receive the prompt (07XX... or +2547XX...).")
        return normalised


class MpesaManualForm(forms.Form):
    amount = AMOUNT
    reference = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control text-uppercase", "placeholder": "e.g. SHL12AB3CD"}),
        help_text="The M-Pesa code from the confirmation SMS (usually 8-10 characters).",
    )
    phone = PHONE
    payment_date = forms.DateField(widget=DATE, required=False)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))

    def clean_reference(self):
        reference = self.cleaned_data["reference"].strip().upper()
        if len(reference) < 6:
            raise ValidationError("That does not look like an M-Pesa code.")
        return reference

    def clean_phone(self):
        normalised = kenyan_phone_to_254(self.cleaned_data["phone"])
        if not normalised:
            raise ValidationError("Enter the number that sent the payment.")
        return normalised


class BankContributionForm(forms.Form):
    amount = AMOUNT
    reference = forms.CharField(
        max_length=60,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Slip number or transfer reference"}),
        help_text="Write the deposit slip number or the bank transfer reference.",
    )
    payment_date = forms.DateField(widget=DATE)
    receipt = forms.ImageField(
        required=False,
        validators=[validate_image_file],
        widget=forms.FileInput(attrs={"class": "form-control", "accept": "image/*"}),
        label="Photo of the slip (optional)",
    )
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))

    def clean_reference(self):
        reference = " ".join(self.cleaned_data["reference"].split())
        if len(reference) < 4:
            raise ValidationError("Give the slip or transfer reference so the treasurer can find it.")
        return reference
