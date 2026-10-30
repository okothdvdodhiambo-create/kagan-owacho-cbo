from django import forms

from apps.core.utils import validate_image_file

from .models import Event, EventReport, EventReportPhoto

WIDGET = forms.TextInput(attrs={"class": "form-control"})
DATETIME = forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["title", "category", "starts_at", "ends_at", "venue", "description", "photo", "published"]
        widgets = {
            "title": WIDGET,
            "venue": WIDGET,
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "photo": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("starts_at", "ends_at"):
            self.fields[name].widget = DATETIME
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["ends_at"].required = False
        self.fields["photo"].validators.append(validate_image_file)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("starts_at"), cleaned.get("ends_at")
        if start and end and end < start:
            self.add_error("ends_at", "The finishing time cannot be before the starting time.")
        return cleaned


class EventReportForm(forms.ModelForm):
    class Meta:
        model = EventReport
        fields = ["event", "title", "body", "published"]
        widgets = {
            "event": forms.Select(attrs={"class": "form-select"}),
            "title": WIDGET,
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 10}),
        }


class EventReportPhotoForm(forms.ModelForm):
    class Meta:
        model = EventReportPhoto
        fields = ["image", "caption"]
        widgets = {"caption": WIDGET, "image": forms.FileInput(attrs={"class": "form-control", "accept": "image/*"})}
