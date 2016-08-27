from __future__ import unicode_literals

import time

from django.db import models
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.contrib.postgres.fields import JSONField


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
    # Here can be added more settings per user
