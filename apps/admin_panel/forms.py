"""Forms used across the custom admin dashboard."""

from django import forms

from apps.contributions.models import Contribution
from apps.incidents.models import IncidentResponse
from apps.membership.models import DropdownOption

WIDGET = forms.TextInput(attrs={"class": "form-control"})


class DropdownOptionForm(forms.ModelForm):
    class Meta:
        model = DropdownOption
        fields = ["field", "label", "order", "active"]
        widgets = {
            "field": forms.Select(attrs={"class": "form-select"}),
            "label": WIDGET,
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }


class IncidentResponseForm(forms.ModelForm):
    class Meta:
        model = IncidentResponse
        fields = ["body", "notify_member"]
        widgets = {"body": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Write the reply the member will see..."})}


class ContributionDecisionForm(forms.Form):
    """The treasurer's verdict on a manual M-Pesa code or bank deposit."""

    decision = forms.ChoiceField(
        choices=[(Contribution.Status.CONFIRMED, "Confirm the payment"), (Contribution.Status.REJECTED, "Reject it")],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    reference = forms.CharField(required=False, max_length=60, widget=WIDGET, label="M-Pesa code / transaction ID (optional)")
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))
