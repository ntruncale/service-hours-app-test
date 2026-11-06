from django import forms

from . import school_year


class OnboardingForm(forms.Form):
    graduation_year = forms.TypedChoiceField(coerce=int, label="Your graduating class")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = school_year.current_school_year()
        self.fields["graduation_year"].choices = [
            (current + i, f"Class of {current + i} (grade {12 - i} this year)") for i in range(4)
        ]
