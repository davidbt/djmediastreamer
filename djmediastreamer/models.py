from __future__ import unicode_literals

import time

from django.db import models
from django.contrib.auth.models import User
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

    def __unicode__(self):
        return self.path
