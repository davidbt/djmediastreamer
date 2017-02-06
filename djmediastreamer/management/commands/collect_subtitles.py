import os
import datetime
import subprocess

import pysrt
import enzyme
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
        'ita': 'italian',
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

    def collect_subtitles_lines(self, subtitle_file, file_path=None):
        if not file_path:
            file_path = os.path.join(
                subtitle_file.directory, subtitle_file.file_name)
        with transaction.atomic():
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
        self.collect_subtitles_lines(subtitle_file)
        return subtitle_file

    def collect_mkv(self, directory, file_name):
        full_path = os.path.join(directory, file_name)
        with open(full_path, 'rb') as fd:
            try:
                mkv = enzyme.MKV(fd)
            except Exception as e:
                print(full_path)
                print(e)
                return
            if mkv.subtitle_tracks:
                # TODO: collect all subtitles
                s = mkv.subtitle_tracks[0]
                # TODO: collect S_TEXT/ASS too
                if s.codec_id == 'S_TEXT/UTF8':
                    temp_file = 'temp_subtitle.srt'
                    cmd = ['mkvextract', 'tracks', full_path,
                           '{n}:{e}'.format(n=s.number - 1, e=temp_file)]
                    subprocess.check_output(cmd)
                    # TODO: guess the language
                    lang = 'simple'
                    rel_mediafile = MediaFile.objects.filter(
                        directory=directory,
                        file_name=file_name).first()
                    subtitle_file = SubtitlesFile.objects.create(
                        file_name=file_name,
                        directory=directory,
                        extension='mkv',
                        mediafile=rel_mediafile,
                        language=lang)
                    self.collect_subtitles_lines(subtitle_file, temp_file)
                    os.remove(temp_file)
                    return subtitle_file
                else:
                    print 'Found other codec id {id} in {f}'.format(
                        id=s.codec_id, f=full_path)

    def collect_subfile(self, directory, file_name):
        subtitle_file = None
        if SubtitlesFile.objects.filter(directory=directory,
                                        file_name=file_name):
            return

        if file_name.lower().endswith('srt'):
            self.collect_srt(directory, file_name)
        elif file_name.lower().endswith('mkv'):
            self.collect_mkv(directory, file_name)

    def handle(self, *args, **options):
        ignore_directories = Directory.objects.filter(ignore=True)
        directory = str(options.get('directory'))
        walk = os.walk(directory)
        for t in walk:
            ignore = False
            d = t[0]
            for ign_dir in ignore_directories:
                if d.startswith(ign_dir.path):
                    ignore = True
                    break
            if ignore:
                continue
            for f in t[2]:
                for ext in settings.SUBTITLE_EXTENSIONS:
                    if f.lower().endswith('.{ext}'.format(ext=ext)):
                        self.collect_subfile(d, f)
