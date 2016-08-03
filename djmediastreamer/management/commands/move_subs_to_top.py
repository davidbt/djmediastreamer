# example: cat file.ass | ./manage.py move_subs_to_top

import os
import sys

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        for line in sys.stdin:
            split = line.split(',')
            if len(split) > 9 and line.startswith('Dialogue'):
                replace = r'{\an8}' + line[:-1].split(',')[9]
                split[9] = replace
                line = ','.join(split)
            print line[:-1]
