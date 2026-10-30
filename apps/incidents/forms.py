from django import forms

from .models import Incident

WIDGET = forms.TextInput(attrs={"class": "form-control"})


class IncidentForm(forms.ModelForm):
    class Meta:
        model = Incident
        fields = ["title", "occurred_on", "description", "attachment"]
        widgets = {
            "title": WIDGET,
            "occurred_on": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 7}),
            "attachment": forms.FileInput(attrs={"class": "form-control"}),
        }

    def clean_title(self):
        title = " ".join(self.cleaned_data["title"].split())
        if len(title) < 5:
            raise forms.ValidationError("Give the report a short but clear title.")
        return title


class IncidentStatusForm(forms.ModelForm):
    """Used by an admin when moving a report through the inbox."""

    class Meta:
        model = Incident
        fields = ["status", "handling_admin"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "handling_admin": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounts.models import User

        self.fields["handling_admin"].required = False
        self.fields["handling_admin"].queryset = User.objects.filter(is_admin=True)
