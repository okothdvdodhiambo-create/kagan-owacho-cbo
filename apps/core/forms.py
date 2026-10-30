"""Forms for admin-editable layout/content (used by the custom admin dashboard)."""

from django import forms

from .models import NavItem, SiteSettings, SliderImage, SocialLink

TEXTAREA = forms.Textarea(attrs={"rows": 4, "class": "form-control"})
INPUT = forms.TextInput(attrs={"class": "form-control"})


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        exclude = ("updated_by", "updated_at")
        widgets = {
            "organization_name": INPUT,
            "motto": INPUT,
            "footer_note": TEXTAREA,
            "home_heading": INPUT,
            "home_subheading": INPUT,
            "home_body": TEXTAREA,
            "home_call_to_action": INPUT,
            "home_statistics_note": INPUT,
            "about_mission": TEXTAREA,
            "about_vision": TEXTAREA,
            "about_history": TEXTAREA,
            "about_leadership": TEXTAREA,
            "whatsapp_number": INPUT,
            "contact_email": INPUT,
            "postal_address": INPUT,
            "location_label": INPUT,
            "map_embed_url": TEXTAREA,
            "bank_name": INPUT,
            "bank_account_name": INPUT,
            "bank_account_number": INPUT,
            "bank_branch": INPUT,
            "bank_notes": TEXTAREA,
            "mpesa_paybill": INPUT,
            "mpesa_account_number": INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["logo"].required = False
        self.fields["map_embed_url"].widget.attrs["rows"] = 3


class SliderImageForm(forms.ModelForm):
    class Meta:
        model = SliderImage
        fields = ["image", "caption", "order", "active"]
        widgets = {"caption": INPUT, "order": forms.NumberInput(attrs={"class": "form-control", "min": 0})}


class SocialLinkForm(forms.ModelForm):
    class Meta:
        model = SocialLink
        fields = ["platform", "url", "order", "active"]
        widgets = {"url": INPUT, "platform": forms.Select(attrs={"class": "form-control"})}


class NavItemForm(forms.ModelForm):
    class Meta:
        model = NavItem
        fields = ["title", "url", "order", "visible"]
        widgets = {"title": INPUT, "url": INPUT}
