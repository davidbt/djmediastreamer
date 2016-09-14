import json

from channels import Group
from django.dispatch import receiver
from django.db.models.signals import post_save
from channels.auth import channel_session_user_from_http

from .models import MediaFileLog


@receiver(post_save, sender=MediaFileLog)
def post_save_MediaFileLog_handler(sender, **kwargs):
    data = {
        'user': kwargs['instance'].user.username,
        'file': kwargs['instance'].mediafile.file_name,
        'directory': kwargs['instance'].mediafile.directory,
    }
    Group('admins').send({'text': json.dumps(data)})


@channel_session_user_from_http
def ws_add(message):
    if message.user.is_staff:
        Group('admins').add(message.reply_channel)


def ws_disconnect(message):
    Group('admins').discard(message.reply_channel)
