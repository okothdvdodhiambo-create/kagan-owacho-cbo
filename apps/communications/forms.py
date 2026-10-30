from django import forms

from .models import ContactMessage, EmailCampaign

WIDGET = forms.TextInput(attrs={"class": "form-control"})
AREA = forms.Textarea(attrs={"class": "form-control", "rows": 6})


class ContactMessageForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "subject", "message"]
        widgets = {"name": WIDGET, "email": forms.EmailInput(attrs={"class": "form-control"}), "phone": WIDGET, "subject": WIDGET, "message": AREA}


class EmailCampaignForm(forms.ModelForm):
    class Meta:
        model = EmailCampaign
        fields = ["subject", "message", "audience", "members", "send_sms"]
        widgets = {"subject": WIDGET, "message": AREA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].required = False
        self.fields["members"].widget = forms.CheckboxSelectMultiple()
        self.fields["members"].queryset = self.fields["members"].queryset.filter(verified=True).order_by("full_name")
