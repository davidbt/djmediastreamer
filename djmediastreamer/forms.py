from django import forms

from .models import Directory
from .utils import get_extensions


class StatisticsFiltersForm(forms.Form):
    directory = forms.ModelChoiceField(
        required=False,
        queryset=Directory.objects.filter(ignore=False),
        empty_label='(All)'
    )
    extension = forms.ChoiceField(
        required=False,
        choices=get_extensions,
    )
