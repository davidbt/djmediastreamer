from __future__ import unicode_literals

import time

from django.db import models
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.contrib.postgres.fields import JSONField

from .fields import TsVectorField


class MediaFile(models.Model):
    file_name = models.TextField()
    directory = models.TextField()
    extension = models.CharField(max_length=5)
    size = models.BigIntegerField(null=True, blank=True)
    md5 = models.TextField(null=True, blank=True)
    duration = models.BigIntegerField(null=True, blank=True)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    a_codec = models.TextField(null=True, blank=True)
    v_codec = models.TextField(null=True, blank=True)
    props = JSONField(null=True, blank=True)

    @property
    def full_path(self):
        return '{d}/{fn}'.format(d=self.directory, fn=self.file_name)

    @property
    def resolution(self):
        return '{w}x{h}'.format(w=self.width, h=self.height)

    @property
    def str_duration(self):
        return time.strftime("%H:%M:%S", time.gmtime(self.duration))

    @property
    def str_size(self):
        return '{0:0.1f} MB'.format(float(self.size) / 2 ** 20)

    @property
    def watch_url(self):
        return reverse('watch_mediafile', args=(self.id,))

    @property
    def download_url(self):
        return reverse('download_mediafile', args=(self.id,))

    def __unicode__(self):
        return self.file_name


class Directory(models.Model):
    path = models.TextField(unique=True)
    to_watch = models.NullBooleanField()
    already_watched = models.NullBooleanField()
    type = models.TextField(null=True, blank=True)
    disk = models.CharField(max_length=100, null=True, blank=True)
    ignore = models.BooleanField(default=False)
    allowed_users = models.ManyToManyField(
        User, blank=True, related_name='directories'
    )

    @property
    def url(self):
        return reverse('mediafiles', args=(self.id,))

    @property
    def collect_url(self):
        return reverse('collect', args=(self.id,))

    def __unicode__(self):
        return self.path


class MediaFileLog(models.Model):
    mediafile = models.ForeignKey(MediaFile)
    user = models.ForeignKey(User)
    dtm = models.DateTimeField(auto_now=True)
    request = models.TextField()
    request_params = JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(default='127.0.0.1')
    # only useful when is streaming
    last_position = models.IntegerField(null=True, blank=True)


class UserSettings(models.Model):
    user = models.OneToOneField(User, related_name='settings')
    max_width = models.IntegerField(null=True, blank=True)
    # Constant Rate Factor. Lower means better quality
    vp8_crf = models.IntegerField(null=True, blank=True)
    # Here can be added more settings per user

    def __unicode__(self):
        return self.user.username


class SubtitlesFile(models.Model):
    file_name = models.TextField()
    directory = models.TextField()
    extension = models.CharField(max_length=5)
    mediafile = models.ForeignKey(MediaFile, null=True, blank=True,
                                  related_name='subtitles')
    language = models.TextField(null=True, blank=True)

    @property
    def is_internal(self):
        return self.file_name.lower().endswith('.mkv')


class SubtitlesLine(models.Model):
    subtitlefile = models.ForeignKey(SubtitlesFile, related_name='lines')
    index = models.IntegerField(db_index=True, null=True, blank=True)
    start = models.TimeField(db_index=True)
    end = models.TimeField(db_index=True)
    text = models.TextField()
    text_vector = TsVectorField(null=True, blank=True)

    def time_to_secods(self, time):
        return time.hour * 3600 + time.minute * 60 + time.second + \
            time.microsecond * 0.000001

    def str_time(self, tmp):
        s = str(tmp)
        if '.' in s:
            split = s.split('.')
            end = split[-1]
            while end.endswith('0') and len(end) > 3:
                end = end[:-1]
            res = '.'.join(split[:-1]) + ',' + end

            return res
        else:
            return s + ',000'

    @property
    def str_start(self):
        return self.str_time(self.start)

    @property
    def str_end(self):
        return self.str_time(self.end)

    @property
    def start_in_seconds(self):
        return self.time_to_secods(self.start)

    @property
    def end_in_seconds(self):
        return self.time_to_secods(self.end)


class TranscodeLog(models.Model):
    mediafile = models.ForeignKey(MediaFile)
    user = models.ForeignKey(User)
    dtm = models.DateTimeField(auto_now=True)
    command = models.TextField()
