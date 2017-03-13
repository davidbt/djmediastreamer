import os
import codecs

from django.core.management.base import BaseCommand

from djmediastreamer.models import SubtitlesFile


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            '--id',
            required=True,
            type=int,
            help='Id of subtitle object to export.'
        )
        parser.add_argument(
            '--output-file',
            required=True,
            type=str,
            help='Output file path.'
        )

    def handle(self, *args, **options):
        sub_file = SubtitlesFile.objects.get(id=options['id'])
        lines = sub_file.lines.order_by('start')
        with codecs.open(options['output_file'], 'w', 'utf-8') as desc:
            for line in lines:
                desc.write(str(line.index) + os.linesep)
                desc.write(
                    line.str_start + ' --> ' + line.str_end + os.linesep)
                desc.write(line.text + os.linesep)
                desc.write(os.linesep)
