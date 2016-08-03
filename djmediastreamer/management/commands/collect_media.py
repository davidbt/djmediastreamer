# example: find / 2>/dev/null | ./manage.py collect_media --with-mediainfo

import os
import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from mymedia.utils import MediaInfo
from mymedia.models import MediaFile, Directory


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
            help='Collect MD5sum.',
        )

    def handle(self, *args, **options):
        ignore_directories = Directory.objects.filter(ignore=True)
        for line in sys.stdin:
            ignore = False
            f = line[:-1]
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
                    print f
