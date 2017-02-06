import os
import datetime

import pysrt
from django.conf import settings
from django.db import transaction
from django.core.management.base import BaseCommand
from django.contrib.postgres.search import SearchVector

from djmediastreamer.models import (MediaFile, Directory, SubtitlesFile,
                                    SubtitlesLine)


class Command(BaseCommand):
    languages = {
        'spa': 'spanish',
        'esp': 'spanish',
        'eng': 'english',
        'ger': 'german',
        'fre': 'french',
        'por': 'portuguese',
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--directory',
            # should be True but call_command fails when is True
            required=False,
            type=str,
            help='The directory path to scan.'
        )

    def guess_language(self, file_name):
        lang_key = file_name.lower().split('.')[-2]
        lang = self.languages.get(lang_key)
        return lang

    def collect_subtitles_lines(self, subtitle_file):
        with transaction.atomic():
            file_path = os.path.join(
                subtitle_file.directory, subtitle_file.file_name)
            try:
                subs = pysrt.open(file_path)
            except UnicodeDecodeError:
                subs = pysrt.open(
                    file_path,
                    encoding='iso-8859-1')
            for sub in subs:
                start = str(datetime.timedelta(
                    milliseconds=sub.start.ordinal))
                end = str(datetime.timedelta(
                    milliseconds=sub.end.ordinal))
                text = sub.text
                line = SubtitlesLine.objects.create(
                    subtitlefile=subtitle_file,
                    index=sub.index,
                    start=str(start),
                    end=str(end),
                    text=text,
                )
                line.text_vector = SearchVector('text',
                                                config=subtitle_file.language)
                line.save()

    def collect_srt(self, directory, file_name):
        # use postgresql "simple" directory if it can't be guessed
        lang = self.guess_language(file_name) or 'simple'
        mediafiles = MediaFile.objects.filter(directory=directory)
        rel_mediafile = None
        for mf in mediafiles:
            if file_name.lower().startswith(
                    '.'.join(mf.file_name.lower().split('.')[:-1])):
                rel_mediafile = mf
                # TODO: maybe look for another match
                break
        subtitle_file = SubtitlesFile.objects.create(
            file_name=file_name,
            directory=directory,
            extension='srt',
            mediafile=rel_mediafile,
            language=lang)
        return subtitle_file

    def collect_subfile(self, directory, file_name):
        subtitle_file = None
        if SubtitlesFile.objects.filter(directory=directory,
                                        file_name=file_name):
            return

        if file_name.lower().endswith('srt'):
            subtitle_file = self.collect_srt(directory, file_name)
        else:
            pass
            # TODO: collect mkv files
        if subtitle_file:
            self.collect_subtitles_lines(subtitle_file)

    def handle(self, *args, **options):
        ignore_directories = Directory.objects.filter(ignore=True)
        directory = str(options.get('directory'))
        walk = os.walk(directory)
        for t in walk:
            ignore = False
            d = t[0]
            for ign_dir in ignore_directories:
                if d.startswith(ign_dir):
                    ignore = True
                    break
            if ignore:
                continue
            for f in t[2]:
                for ext in settings.SUBTITLE_EXTENSIONS:
                    if f.lower().endswith('.{ext}'.format(ext=ext)):
                        self.collect_subfile(d, f)
