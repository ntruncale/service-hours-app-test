from django import forms

from accounts import school_year

from .models import ServiceEntry


class ServiceEntryForm(forms.ModelForm):
    class Meta:
        model = ServiceEntry
        fields = [
            "service_date",
            "hours",
            "organization",
            "location",
            "category",
            "description",
            "supervisor_name",
            "supervisor_email",
            "supervisor_phone",
        ]
        widgets = {
            "service_date": forms.DateInput(attrs={"type": "date"}),
            "hours": forms.NumberInput(
                attrs={"step": "0.25", "min": "0.25", "inputmode": "decimal"}
            ),
            "description": forms.Textarea(attrs={"rows": 3}),
            "supervisor_email": forms.EmailInput(attrs={"autocapitalize": "off"}),
            "supervisor_phone": forms.TextInput(attrs={"type": "tel"}),
        }
        labels = {
            "service_date": "Date of service",
            "hours": "Hours",
            "organization": "Organization",
            "location": "Location (city or address)",
            "supervisor_name": "Supervisor's name",
            "supervisor_email": "Supervisor's email",
            "supervisor_phone": "Supervisor's phone",
        }
        help_texts = {
            "supervisor_email": "We'll email this person a link to confirm your hours.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service_date"].widget.attrs["max"] = school_year.today().isoformat()


class SupervisorDecisionForm(forms.Form):
    typed_name = forms.CharField(
        max_length=150,
        label="Type your full name to sign",
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )
    comment = forms.CharField(
        required=False,
        max_length=1000,
        label="Comment (optional)",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("decline", "Decline")])

    def clean(self):
        data = super().clean()
        if data.get("decision") == "decline" and not data.get("comment", "").strip():
            self.add_error("comment", "Please tell the student why you can't confirm these hours.")
        return data
