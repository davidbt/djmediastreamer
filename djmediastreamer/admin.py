from django.contrib import admin

from .models import MediaFile, Directory


class DirectoryAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'path', 'to_watch', 'already_watched', 'type', 'disk', 'ignore'
    )
    filter_horizontal = ('allowed_users',)


class MediaFileAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'file_name', 'directory', 'extension', 'size', 'duration',
        'width', 'height', 'a_codec', 'v_codec'
    )
    search_fields = ('file_name', 'directory', 'a_codec')

admin.site.register(MediaFile, MediaFileAdmin)
admin.site.register(Directory, DirectoryAdmin)
