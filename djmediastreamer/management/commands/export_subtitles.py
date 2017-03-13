import os
import codecs
import datetime

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
        parser.add_argument(
            '--keep-subtitles',
            required=False,
            type=bool,
            default=False,
            help='Keeps the text in the screen for more time when is possible.'
        )

    def handle(self, *args, **options):
        sub_file = SubtitlesFile.objects.get(id=options['id'])
        lines = [l for l in sub_file.lines.order_by('start')]
        keep = options['keep_subtitles']
        with codecs.open(options['output_file'], 'w', 'utf-8') as desc:
            for i, line in enumerate(lines):
                end = line.end

                if keep and i < len(lines) - 1:
                    next_line = lines[i + 1]
                    end_in_seconds = line.end_in_seconds + 5
                    if end_in_seconds > next_line.start_in_seconds:
                        end_in_seconds = next_line.start_in_seconds - 0.2
                    end = datetime.time(
                        hour=int(end_in_seconds) / 3600,
                        minute=(int(end_in_seconds) % 3600) / 60,
                        second=(int(end_in_seconds) % 3600) % 60,
                        microsecond=int(end_in_seconds - int(end_in_seconds)) * 1000000
                    )
                    if end < line.end:
                        # back to where we started
                        end = line.end

                end = line.str_time(end)
                desc.write(str(line.index) + os.linesep)

                desc.write(
                    line.str_start + ' --> ' + end + os.linesep)
                desc.write(line.text + os.linesep)
                desc.write(os.linesep)
