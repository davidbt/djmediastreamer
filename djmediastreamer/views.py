import os
import subprocess

from django.db.models import Q

from sendfile import sendfile
from django.core import management
from django.core.urlresolvers import reverse
from django.views.generic import TemplateView, View
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import login, logout, authenticate
from django.http import (
    StreamingHttpResponse, HttpResponseRedirect, HttpResponseForbidden
)


from .models import MediaFile, Directory
from .utils import (
    MediaInfo, get_allowed_directories, can_access_directory,
    can_access_mediafile, get_subtitles_from_request
)


class LogoutView(View):
    def get(self, request, *args, **kwargs):
        logout(request)
        return HttpResponseRedirect(reverse('login'))


class LoginView(TemplateView):
    template_name = "djmediastreamer/login.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {})

    def post(self, request, *args, **kwargs):
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                return HttpResponseRedirect(request.GET.get('next', '/'))
            else:
                pass
                # TODO: Return a 'disabled account' error message.
        else:
            pass
            # TODO: Return an 'invalid login' error message.


class DirectoriesView(LoginRequiredMixin, TemplateView):
    login_url = '/login/'
    redirect_field_name = 'next'
    template_name = "djmediastreamer/directories.html"

    def get(self, request, *args, **kwargs):
        context = {}
        ds = get_allowed_directories(request.user).order_by('path')
        directories = []
        for d in ds:
            directories.append(d)
        context['directories'] = directories
        return render(request, self.template_name, context)


class MediaFilesView(LoginRequiredMixin, TemplateView):
    login_url = '/login/'
    redirect_field_name = 'next'
    template_name = "djmediastreamer/mediafiles.html"

    def get(self, request, id, *args, **kwargs):
        context = {}
        d = get_object_or_404(Directory, id=id)
        if not can_access_directory(request.user, d):
            return HttpResponseForbidden()

        mfs = MediaFile.objects.filter(
            directory__startswith=d.path
        ).order_by('file_name')
        mediafiles = []
        for mf in mfs:
            mf.subdirectory = mf.directory[len(d.path) + 1:]
            mediafiles.append(mf)
        context['mediafiles'] = mfs
        context['directory'] = d
        return render(request, self.template_name, context)


class WatchMediaFileView(LoginRequiredMixin, TemplateView):
    login_url = '/login/'
    redirect_field_name = 'next'
    template_name = "djmediastreamer/watch.html"

    def lookfor_subtitles(self, mediafile):
        files = os.listdir(mediafile.directory)
        subtitles = []
        for f in files:
            split = f.split('.')
            ext = split[-1].lower()
            if ext in ['srt', 'ass'] and (
                '.'.join(mediafile.file_name.split('.')[:-1]) in f
            ):
                subtitles.append(f)
        return subtitles

    def get(self, request, id, *args, **kwargs):
        context = {}
        mf = get_object_or_404(MediaFile, id=id)
        if not can_access_mediafile(request.user, mf):
            return HttpResponseForbidden()
        mf.url = reverse('get_mediafile', args=(mf.id,))
        goto = request.GET.get('goto')
        if goto:
            mf.url += '?goto={g}'.format(g=goto)

        selected_subs, url_append = get_subtitles_from_request(request)
        mf.url += url_append
        mf.video_type = 'video/webm'

        if mf.extension == 'mp4' and mf.v_codec == 'AVC':
            mf.video_type = 'video/mp4'
        context['mediafile'] = mf

        subtitles_avail = self.lookfor_subtitles(mf)
        subtitles = []
        for s in subtitles_avail:
            if s in selected_subs:
                subtitles.append({'file': s, 'checked': 'checked'})
            else:
                subtitles.append({'file': s, 'checked': ''})
        context['subtitles'] = subtitles
        context['goto'] = goto or '00:00:00'
        for d in get_allowed_directories(request.user):
            if mf.directory.startswith(d.path):
                directory = d
                break
        context['directory'] = directory
        return render(request, self.template_name, context)


class GethMediaFileView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def prepare_subtitles(self, s):
        output = subprocess.check_output(['file', s])
        cmd = None
        split = s.split('.')
        n = '.'.join(split[:-1])
        new_name = '{n}.UTF8.{ext}'.format(n=n, ext=split[-1])
        if 'ISO-8859' in output or 'Non-ISO extended-ASCII' in output:
            cmd = 'iconv --from-code=ISO-8859-1 --to-code=UTF-8 "{s}" > "{n}"'\
                .format(s=s, n=new_name)
        elif 'ASCII' in output:
            cmd = 'iconv --from-code=ASCII --to-code=UTF-8 "{s}" > "{n}"'\
                .format(s=s, n=new_name)
        if cmd:
            os.system(cmd)
            return new_name
        return s

    def read_mediafile(self, full_path):
        with open(full_path, 'rb') as f:
            r = True
            while r:
                r = f.read(1024*8)
                yield r

    def transcode_process(
        self, full_path, subtitles=None, goto=None, output_format='webm'
    ):
        if output_format == 'webm':
            cmd = [
                'ffmpeg', '-i', full_path, '-codec:v', 'vp8', '-b:v', '0',
                '-crf', '24', '-threads', '8', '-speed', '4'
            ]
            extend = ['-f', 'webm', '-']
        elif output_format == 'matroska':
            cmd = [
                'ffmpeg', '-i', full_path,
                '-crf', '20'
            ]
            extend = ['-f', 'matroska', '-']
        if goto:
            cmd.extend(['-ss', goto])
        if subtitles:
            for i in range(len(subtitles)):
                subtitles[i] = self.prepare_subtitles(subtitles[i])
            if len(subtitles) == 1:
                cmd.extend(['-vf', 'subtitles={s}'.format(s=subtitles[0])])
            else:
                subs_out = '.'.join(full_path.split('.')[:-1]) + '__.ass'
                subtitles_cmd = 'ffmpeg -i "{s1}" -f ass - | ./manage.py move_subs_to_top > "{out}"' \
                    .format(s1=subtitles[1], out=subs_out)
                os.system(subtitles_cmd)
                cmd.extend(['-vf', 'subtitles={s0},ass={s1}'.format(
                    s0=subtitles[0], s1=subs_out)]
                )
        cmd.extend(extend)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        return p

    def stream_video(
        self, full_path, subtitles=None, goto=None, output_format='webm'
    ):
        p = self.transcode_process(full_path, subtitles, goto, output_format)
        p.poll()
        while p.returncode is None:
            r = p.stdout.read(512)
            p.poll()
            yield r
        r = p.stdout.read()
        yield r

    def get_subtitles_files(self, mediafile):
        # TODO: return all subtitles, not only one
        if mediafile.extension == 'mkv':
            mi = MediaInfo(mediafile.full_path)
            index = mi.get_mkv_subtitles_index()
            if index is not None:
                return [mi.extract_mkv_subtitles(mediafile.id, index)]
        return []

    def get(self, request, id, *args, **kwargs):
        mf = get_object_or_404(MediaFile, id=id)
        if not can_access_mediafile(request.user, mf):
            return HttpResponseForbidden()
        subtitles, _ = get_subtitles_from_request(request)
        if subtitles:
            # max two subtitles
            subtitles = [os.path.join(mf.directory, s) for s in subtitles[:2]]
        else:
            subtitles = self.get_subtitles_files(mf)

        goto = request.GET.get('goto')
        if mf.extension == 'mp4' and mf.v_codec == 'AVC' and (
            (not goto) and (not subtitles)
        ):
            return sendfile(request, mf.full_path)
        else:
            output_format = 'webm'
            if 'Chrome' in request.META['HTTP_USER_AGENT']:
                output_format = 'matroska'
            return StreamingHttpResponse(
                self.stream_video(
                    mf.full_path, subtitles, goto, output_format),
                content_type='video/webm'
            )


class DownloadMediaFileView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, id, *args, **kwargs):
        mf = get_object_or_404(MediaFile, id=id)
        if not can_access_mediafile(request.user, mf):
            return HttpResponseForbidden()
        return sendfile(request, mf.full_path, attachment=True)


class CollectDirectoryView(LoginRequiredMixin, View):
    def get(self, request, id, *args, **kwargs):
        d = get_object_or_404(Directory, id=id)
        if not can_access_directory(request.user, d):
            return HttpResponseForbidden()
        management.call_command(
            'collect_media',
            with_mediainfo=True,
            directory=d.path,
            remove_missing=True
        )
        return HttpResponseRedirect(reverse('directories'))
