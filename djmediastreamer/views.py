import os
import time
import subprocess

from sendfile import sendfile
from django.core import management
from django.core.urlresolvers import reverse
from django.views.generic import TemplateView, View
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import login, logout, authenticate
from django.http import (
    HttpResponseRedirect, HttpResponseForbidden, JsonResponse,
    StreamingHttpResponse
)


from .models import MediaFile, Directory, MediaFileLog, UserSettings
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
                return render(
                    request, self.template_name, {'error': 'Disabled account'}
                )
        else:
            return render(
                request, self.template_name, {'error': 'Invalid login'}
            )


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
            mfls = MediaFileLog.objects.filter(
                mediafile=mf, user=request.user, last_position__isnull=False
            ).order_by('-dtm')
            if mfls:
                mlf = mfls.first()
                time_zero = time.mktime(time.strptime('00:00:00', '%H:%M:%S'))
                initial = time.mktime(
                    time.strptime(
                        mlf.request_params.get('goto', '00:00:00'), '%H:%M:%S')
                )
                new_initial = initial - time_zero + mlf.last_position
                mf.last_position = MediaFile(duration=new_initial).str_duration
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
        mf.transcoded_url = mf.url
        trnscoded_append = 'download=true'
        if '?' in mf.transcoded_url:
            mf.transcoded_url += '&' + trnscoded_append
        else:
            mf.transcoded_url += '?' + trnscoded_append
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
            if (mf.directory + '/').startswith(d.path + '/'):
                directory = d
                break
        context['directory'] = directory
        MediaFileLog.objects.create(
            mediafile=mf,
            user=request.user,
            request=request.path,
            request_params=request.GET,
            ip=request.META.get('HTTP_X_REAL_IP', request.META['REMOTE_ADDR'])
        )
        return render(request, self.template_name, context)

    def put(self, request, id, *args, **kwargs):
        mf = get_object_or_404(MediaFile, id=id)
        if not can_access_mediafile(request.user, mf):
            return HttpResponseForbidden()
        mfls = MediaFileLog.objects.filter(
            mediafile=mf, user=request.user
        ).order_by('-dtm')
        mfl = mfls.first()
        split = request.body.split('=')
        position = float(split[1])
        mfl.last_position = int(position)
        mfl.ip = request.META.get(
            'HTTP_X_REAL_IP', request.META['REMOTE_ADDR']
        )
        mfl.save()
        return JsonResponse({})


class GethMediaFileView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def prepare_subtitles(self, s, offset=None):
        res = s
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
            res = new_name
        if offset:
            split = res.split('.')
            n = '.'.join(split[:-1])
            new_name = '{n}.ss.{ext}'.format(n=n, ext=split[-1])
            cmd = 'ffmpeg -i {res} -ss {offset}  -f {ext} {nn}'.format(
                res=res, offset=offset, ext=split[-1], nn=new_name
            )
            os.system(cmd)
            res = new_name

        return res

    def transcode_process(
        self, full_path, subtitles=None, goto=None, output_format='webm',
        width=None, height=None
    ):
        if output_format == 'webm':
            cmd = ['ffmpeg', '-i', full_path]
            if width:
                cmd.extend(['-s',  '{mw}x{h}'.format(mw=width, h=height)])
            cmd.extend([
                '-codec:v', 'vp8', '-b:v', '0', '-crf', '24',
                '-threads', '8', '-speed', '4'
            ])

            extend = ['-f', 'webm', '-']
        elif output_format == 'matroska':
            cmd = [
                'ffmpeg', '-i', full_path,
                '-crf', '20'
            ]
            extend = ['-f', 'matroska', '-']
        if goto:
            cmd.insert(1, '-ss')
            cmd.insert(2, goto)
        if subtitles:
            for i in range(len(subtitles)):
                subtitles[i] = self.prepare_subtitles(subtitles[i], goto)
            if len(subtitles) == 1:
                cmd.extend(['-vf', 'subtitles={s}'.format(s=subtitles[0])])
            else:
                subs_out = '.'.join(full_path.split('.')[:-1]) + '__.ass'
                subtitles_cmd = 'ffmpeg -i "{s1}" -f ass - | ./manage.py move_subs_to_top > "{out}"'.format(s1=subtitles[1], out=subs_out)  # noqa
                os.system(subtitles_cmd)
                cmd.extend(['-vf', 'subtitles={s0},ass={s1}'.format(
                    s0=subtitles[0], s1=subs_out)]
                )
        cmd.extend(extend)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        return p

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
            fn = '.'.join(mf.file_name.split('.')[:-1])
            output_format = 'webm'
            if 'Chrome' in request.META['HTTP_USER_AGENT']:
                output_format = 'matroska'
                fn += '.mkv'
            else:
                fn += '.webm'
            width = None
            height = None
            if UserSettings.objects.filter(user=request.user):
                max_width = request.user.settings.max_width \
                    if request.user.settings else None
                width = max_width if mf.width > max_width else None
                height = mf.height * width / mf.width if width else None
            res = StreamingHttpResponse(
                self.transcode_process(
                    mf.full_path, subtitles, goto, output_format, width, height
                ).stdout,
                content_type='video/webm',
            )
            res['Content-Disposition'] = 'filename="{fn}"'.format(fn=fn)
            if request.GET.get('download') == 'true':
                res['Content-Disposition'] = 'attachment; {cd}'.format(
                    cd=res['Content-Disposition'])
            return res


class DownloadMediaFileView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, id, *args, **kwargs):
        mf = get_object_or_404(MediaFile, id=id)
        if not can_access_mediafile(request.user, mf):
            return HttpResponseForbidden()
        MediaFileLog.objects.create(
            mediafile=mf,
            user=request.user,
            request=request.path,
            request_params=request.GET
        )
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
