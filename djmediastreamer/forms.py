from django import forms
from django.conf import settings

from .models import Directory
from .utils import get_extensions, get_video_codecs


def get_languages():
    return [(v, v) for v in set(settings.LANGUAGES.values())]


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


class SearchSubtitlesForm(forms.Form):
    query = forms.CharField()
    language = forms.ChoiceField(choices=get_languages)
