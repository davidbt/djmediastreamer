# example: find / 2>/dev/null | ./manage.py collect_media --with-mediainfo

import os
import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from djmediastreamer.utils import MediaInfo
from djmediastreamer.models import MediaFile, Directory


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            '--with-mediainfo',
            action='store_true',
            dest='with_mediainfo',
            default=False,
            help='Collect Mediainfo data.',
        )
        parser.add_argument(
            '--with-md5',
            action='store_true',
            dest='with_md5',
            default=False,
            help='Collect MD5sum (not implemented yet).',
        )
        parser.add_argument(
            '--directory',
            required=False,
            type=str,
            help='The directory path to scan. If not given, it will scan the files that are given to the standar input.'  # noqa
        )
        parser.add_argument(
            '--remove-missing',
            action='store_true',
            dest='remove_missing',
            default=False,
            help='Removes MediaFiles from the DB associated with files that no longer exists in the selected directory.',  # noqa
        )

    def handle(self, *args, **options):
        ignore_directories = Directory.objects.filter(ignore=True)
        lines = sys.stdin
        directory = str(options.get('directory'))
        if directory:
            lines = []
            walk = os.walk(directory)
            for t in walk:
                d = t[0]
                for f in t[2]:
                    #  TODO: just add the video files.
                    lines.append(os.path.join(t[0], f))

        for line in lines:
            ignore = False
            f = line.strip()
            l = f.lower()
            for d in ignore_directories:
                if f.startswith(str(d.path)):
                    ignore = True
            if ignore:
                continue
            for e in settings.VIDEO_EXTENSIONS:
                if l.endswith('.' + e):
                    split = f.split('/')
                    n = split[-1]
                    path = '/'.join(split[:-1])
                    ext = n.split('.')[-1].lower()
                    s = os.path.getsize(f)
                    mf = MediaFile.objects.filter(file_name=n, directory=path)
                    if mf:
                        mf = mf.first()
                        found = True
                    else:
                        mf = MediaFile(
                            file_name=n,
                            directory=path,
                            extension=ext,
                            size=s,
                        )
                        if options.get('with_mediainfo'):
                            mi = MediaInfo(f)
                            mf.width, mf.height = mi.get_size()
                            mf.v_codec = mi.get_video_codec()
                            mf.a_codec = mi.get_audio_codec()
                            mf.duration = mi.get_duration()
                        found = False
                        mf.save()
                    break

        if options.get('remove_missing'):
            mediafiles = MediaFile.objects.all()
            if directory:
                if not os.path.exists(directory):
                    print 'Skiping because the directory does not exists.'
                    return
                mediafiles = mediafiles.filter(directory__startswith=directory)
            for mf in mediafiles:
                if not os.path.exists(mf.full_path):
                    mf.delete()
