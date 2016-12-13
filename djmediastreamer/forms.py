from django import forms

from .models import Directory
from .utils import get_extensions, get_video_codecs


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
    video_codec = forms.ChoiceField(
        required=False,
        choices=get_video_codecs,
    )
    to_chart = forms.ChoiceField(
        required=False,
        choices=[('count', 'Count'), ('size', 'Size (Gb)')],
    )
