import os
import time
import subprocess
from collections import OrderedDict

from sendfile import sendfile
from django.conf import settings
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


from .forms import StatisticsFiltersForm
from .models import (
    MediaFile, Directory, MediaFileLog, UserSettings, SubtitlesFile
)
from .utils import (
    MediaInfo, get_allowed_directories, can_access_directory,
    can_access_mediafile, get_subtitles_from_request, plot_query,
    str_duration_to_seconds, execute_query
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
            mf.subtitles_langs = ', '.join([
                s.language for s in mf.subtitles.all()])
            mediafiles.append(mf)
            mfls = MediaFileLog.objects.filter(
                mediafile=mf, user=request.user, last_position__isnull=False
            ).order_by('-dtm')
            if mfls:
                mlf = mfls.first()
                time_zero = time.mktime(time.strptime('00:00:00', '%H:%M:%S'))
                goto = mlf.request_params.get('goto', '00:00:00')
                if goto.endswith('%'):
                    seconds = str_duration_to_seconds(goto, mf)
                    goto = MediaFile(duration=seconds).str_duration
                initial = time.mktime(time.strptime(goto, '%H:%M:%S'))
                new_initial = initial - time_zero + mlf.last_position
                mf.last_position = MediaFile(duration=new_initial).str_duration
                mf.progress = int(1.0*new_initial / mf.duration * 100)
        context['mediafiles'] = mfs
        context['directory'] = d
        return render(request, self.template_name, context)


class WatchMediaFileView(LoginRequiredMixin, TemplateView):
    login_url = '/login/'
    redirect_field_name = 'next'
    template_name = "djmediastreamer/watch.html"

    def lookfor_subtitles(self, mediafile):
        return mediafile.subtitles.all()

    def get(self, request, id, *args, **kwargs):
        context = {}
        mf = get_object_or_404(MediaFile, id=id)
        if not can_access_mediafile(request.user, mf):
            return HttpResponseForbidden()
        mf.url = reverse('get_mediafile', args=(mf.id,))
        goto = request.GET.get('goto')
        if goto:
            mf.url += '?goto={g}'.format(g=goto)
            # escape percentage symbol
            if goto.endswith('%'):
                mf.url += '25'

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
        progress = 0
        if goto:
            s = str_duration_to_seconds(goto, mf)
            progress = int((s*1.0 / mf.duration) * 100)
        context['progress'] = progress

        subtitles_avail = self.lookfor_subtitles(mf)
        subtitles = []
        for s in subtitles_avail:
            sub_text = '{id} {l}'.format(id=s.id, l=s.language)
            if s in selected_subs:
                subtitles.append({'file': sub_text, 'checked': 'checked'})
            else:
                subtitles.append({'file': sub_text, 'checked': ''})
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
        initial = str_duration_to_seconds(
            mfl.request_params.get('goto', '00:00:00'), mf
        )
        progress = int(1.0*(initial + mfl.last_position) / mf.duration * 100)
        return JsonResponse({'progress': progress})


class GethMediaFileView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def prepare_subtitles(self, s, offset=None):
        res = s
        if s.is_internal:
            print 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaa' #DELETE
            # TODO: extract mkv subtitle
            pass
        else:
            subtitle_path = os.path.join(s.directory, s.file_name)
        output = subprocess.check_output(['file', subtitle_path])
        cmd = None
        new_name = '{id}.utf8.{ext}'.format(id=s.id, ext=s.extension)
        if 'ISO-8859' in output or 'Non-ISO extended-ASCII' in output:
            cmd = 'iconv --from-code=ISO-8859-1 --to-code=UTF-8 "{s}" > "{n}"'\
                .format(s=subtitle_path, n=new_name)
        elif 'ASCII' in output:
            cmd = 'iconv --from-code=ASCII --to-code=UTF-8 "{s}" > "{n}"'\
                .format(s=subtitle_path, n=new_name)
        if cmd:
            os.system(cmd)
            res = new_name
        if offset:
            split = new_name.split('.')
            n = '.'.join(split[:-1])
            new_name = '{n}.ss.{ext}'.format(n=n, ext=split[-1])
            cmd = 'ffmpeg -i {res} -ss {offset} -f {ext} -y {nn}'.format(
                res=res, offset=offset, ext=split[-1], nn=new_name
            )
            os.system(cmd)
            res = new_name
        return res

    def transcode_process(
        self, full_path, subtitles=None, goto=None, output_format='webm',
        width=None, height=None, vp8_crf=24
    ):
        if output_format == 'webm':
            cmd = ['ffmpeg', '-i', full_path]
            if width:
                cmd.extend(['-s',  '{mw}x{h}'.format(mw=width, h=height)])
            cmd.extend([
                '-codec:v', 'vp8', '-b:v', '0', '-crf', str(vp8_crf),
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
        prepared_subtitles = []
        if subtitles:
            for i, s in enumerate(subtitles):
                prepared_subtitles.append(self.prepare_subtitles(s, goto))
            if len(prepared_subtitles) == 1:
                cmd.extend(['-vf', 'subtitles={s}'.format(
                    s=prepared_subtitles[0])])
            else:
                subs_out = '.'.join(full_path.split('.')[:-1]) + '__.ass'
                subtitles_cmd = 'ffmpeg -i "{s1}" -f ass - | ./manage.py move_subs_to_top > "{out}"'.format(s1=prepared_subtitles[1], out=subs_out)  # noqa
                os.system(subtitles_cmd)
                cmd.extend(['-vf', 'subtitles={s0},ass={s1}'.format(
                    s0=prepared_subtitles[0], s1=subs_out)]
                )
        cmd.extend(extend)
        p = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return p

    def get(self, request, id, *args, **kwargs):
        mf = get_object_or_404(MediaFile, id=id)
        if not can_access_mediafile(request.user, mf):
            return HttpResponseForbidden()
        subtitles, _ = get_subtitles_from_request(request)
        goto = request.GET.get('goto')
        if goto and goto.endswith('%'):
            seconds = str_duration_to_seconds(goto, mf)
            goto = MediaFile(duration=seconds).str_duration
        if mf.extension == 'mp4' and mf.v_codec == 'AVC' and (
            (not goto) and (not subtitles)
        ):
            return sendfile(request, mf.full_path)
        else:
            fn = '.'.join(mf.file_name.split('.')[:-1])
            output_format = 'webm'
            if 'Chrome' in request.META['HTTP_USER_AGENT'] and (
                'Android' not in request.META['HTTP_USER_AGENT']
            ):
                output_format = 'matroska'
                fn += '.mkv'
            else:
                fn += '.webm'
            width = None
            height = None
            vp8_crf = settings.DEFAULT_VP8_CRF
            if UserSettings.objects.filter(user=request.user):
                max_width = request.user.settings.max_width \
                    if request.user.settings else None
                width = max_width if mf.width > max_width else None
                height = mf.height * width / mf.width if width else None
                vp8_crf = request.user.settings.vp8_crf or (
                    settings.DEFAULT_VP8_CRF
                )
            res = StreamingHttpResponse(
                self.transcode_process(
                    mf.full_path, subtitles, goto, output_format, width,
                    height, vp8_crf
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
        management.call_command(
            'collect_subtitles',
            directory=d.path,
        )
        return HttpResponseRedirect(reverse('directories'))


class QueryMediaFilesView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        agg_column = request.GET['to_chart'] or 'count'
        chart = StatisticsView.get_chart_definitions(
            agg_column)[request.GET['chart']]
        query = chart['details_query']
        filters = {}
        filters[chart['details_filter']] = request.GET.get('column_name')
        for f in chart['filters']:
            filters[f] = request.GET.get(f) or None
        if filters.get('directory'):
            d = Directory.objects.get(id=filters['directory'])
            filters['directory'] = d.path
        cursor = execute_query(query, filters)
        columns = [col[0] for col in cursor.description]
        data = [list(r) for r in cursor.fetchall()]
        return JsonResponse({'mediafiles': data, 'columns': columns})


class StatisticsView(LoginRequiredMixin, TemplateView):
    template_name = "djmediastreamer/statistics.html"

    @classmethod
    def get_chart_definitions(cls, agg_column):
        charts = OrderedDict()
        default_filters = [f for f in StatisticsFiltersForm.declared_fields]
        default_columns = ', '.join(['mf.id', 'mf.file_name', 'mf.directory'])
        filters_str = """(directory like %(directory)s || '%%'
            OR %(directory)s is NULL)
        AND (extension = %(extension)s OR %(extension)s is NULL)
        AND (v_codec = %(video_codec)s OR %(video_codec)s is NULL)"""
        agg_columns = {
            'count': 'count(*) as "Count"',
            'size': '(sum(size) / (1024*1024*1024))::decimal(15,2) as "Gb"'
        }
        # chart_by_vcodec #####################################################
        c = {
            'name': 'chart_by_vcodec',
            'container': 'container1',
            'filters': default_filters,
            'details_filter': 'v_codec',
        }
        c['query'] = """select v_codec, {agg_col}
        from djmediastreamer_mediafile
        where
            {filters_str}
        group by v_codec order by 2 asc;""".format(
            filters_str=filters_str,
            agg_col=agg_columns[agg_column])

        c['details_query'] = """select {columns_str}
        from djmediastreamer_mediafile mf
        where
            {filters_str}
            AND v_codec = %(v_codec)s;""".format(
                filters_str=filters_str, columns_str=default_columns
        )
        charts['chart_by_vcodec'] = c

        # chart_by_ext ########################################################
        c = {
            'name': 'chart_by_ext',
            'container': 'container2',
            'filters': default_filters,
            'details_filter': 'ext',
        }
        c['query'] = """select extension, {agg_col}
        from djmediastreamer_mediafile
        where
            {filters_str}
        group by extension order by 2 asc;""".format(
            filters_str=filters_str, agg_col=agg_columns[agg_column])

        c['details_query'] = """select {columns_str}
        from djmediastreamer_mediafile mf
        where
            {filters_str}
            AND extension = %(ext)s;""".format(
                filters_str=filters_str, columns_str=default_columns
        )

        charts['chart_by_ext'] = c

        # chart_by_file_size ##################################################
        c = {
            'name': 'chart_by_file_size',
            'container': 'container3',
            'filters': default_filters,
            'details_filter': 'rnge',
        }
        c['query'] = """with v as (
            select n::bigint * 1048576 as l, n,
            (n::bigint+250)*1048576 as h,
            n::text || ' - ' || (n+250)::text || ' MB' as rnge
            from generate_series(0, 4750, 250) n
        )
        select  n::text || ' - ' || (n+250)::text || ' MB' as rnge,
        {agg_col}
        from djmediastreamer_mediafile mf
        left outer join v on size > l and size <= h
        where
            {filters_str}
        group by n
        order by n;""".format(
            filters_str=filters_str, agg_col=agg_columns[agg_column])

        c['details_query'] = """
        with v as (
            select n::bigint * 1048576 as l, n,
            (n::bigint+250)*1048576 as h,
            n::text || ' - ' || (n+250)::text || ' MB' as rnge
            from generate_series(0, 4750, 250) n
        )
        select {columns_str}
        from djmediastreamer_mediafile mf
        left outer join v on size > l and size <= h
        where
            {filters_str}
            AND rnge = %(rnge)s
        order by n;""".format(
            filters_str=filters_str, columns_str=default_columns
        )

        charts['chart_by_file_size'] = c

        # chart_by_img_size ###################################################
        c = {
            'name': 'chart_by_img_size',
            'container': 'container4',
            'filters': default_filters,
            'details_filter': 'resolution',
        }
        c['query'] = """select width::text || 'x' || height::text as reso, {agg_col}
        from djmediastreamer_mediafile
        where
            {filters_str}
        group by width, height
        order by width;""".format(
            filters_str=filters_str,
            agg_col=agg_columns[agg_column])

        c['details_query'] = """select {columns_str}
        from djmediastreamer_mediafile mf
        where
            {filters_str}
            AND width::text || 'x' || height::text = %(resolution)s
        order by width;""".format(
            filters_str=filters_str, columns_str=default_columns
        )

        charts['chart_by_img_size'] = c

        # chart_by_duration ###################################################
        c = {
            'name': 'chart_by_duration',
            'container': 'container5',
            'filters': default_filters,
            'details_filter': 'duration',
        }
        c['query'] = """with v as (
            select n as l,
            (n+900) as h
            from generate_series(0, 18000, 900) n
        )
        select (l / 60)::text || ' - ' || ((l+900) / 60)::text ||
            ' mins' as duration,
        {agg_col}
        from djmediastreamer_mediafile mf
        left outer join v on mf.duration > l and mf.duration <= h
        where
            {filters_str}
        group by l
        order by l;""".format(
            filters_str=filters_str, agg_col=agg_columns[agg_column])

        c['details_query'] = """with v as (
            select n as l,
            (n+900) as h
            from generate_series(0, 18000, 900) n
        )
        select {columns_str}
        from djmediastreamer_mediafile mf
        left outer join v on mf.duration > l and mf.duration <= h
        where
            {filters_str}
            AND (l / 60)::text || ' - ' || ((l+900) / 60)::text || ' mins' =
                %(duration)s
        order by l;""".format(
            filters_str=filters_str, columns_str=default_columns
        )

        charts['chart_by_duration'] = c

        # chart_by_directory ##################################################
        c = {
            'name': 'chart_by_directory',
            'container': 'container6',
            'filters': default_filters,
            'details_filter': 'dir',  # the clicked bar, not the dropdown
        }
        c['query'] = """select d.path, {agg_col}
        from djmediastreamer_mediafile mf
            left outer join djmediastreamer_directory d on d.path ||
                '/' = substring(mf.directory
                || '/', 1, length(d.path) + 1)
            where (extension = %(extension)s OR %(extension)s is NULL)
                AND (v_codec = %(video_codec)s OR %(video_codec)s is NULL)
        group by d.path
        order by 2;""".format(agg_col=agg_columns[agg_column])

        c['details_query'] = """select {columns_str}
        from djmediastreamer_mediafile mf
            left outer join djmediastreamer_directory d on d.path ||
                '/' = substring(mf.directory
                || '/', 1, length(d.path) + 1)
        where
            (extension = %(extension)s OR %(extension)s is NULL)
            AND (v_codec = %(video_codec)s OR %(video_codec)s is NULL)
            AND d.path = %(dir)s;""".format(columns_str=default_columns)

        charts['chart_by_directory'] = c

        # chart_by_repeated ##################################################
        # repeated files
        c = {
            'name': 'chart_by_repeated',
            'container': 'container7',
            'filters': default_filters,
            'details_filter': 'dir',  # the clicked bar, not the dropdown
        }
        c['query'] = """with v as (
        select d.path, mf1.size
        from djmediastreamer_mediafile mf1
            inner join djmediastreamer_mediafile mf2 on mf2.id > mf1.id
                and mf1.file_name = mf2.file_name
            left outer join djmediastreamer_directory d on d.path ||
                '/' = substring(mf1.directory || '/', 1, length(d.path) + 1)
        where (mf1.extension = %(extension)s OR %(extension)s is NULL)
            AND (mf1.v_codec = %(video_codec)s OR %(video_codec)s is NULL)
        )
        select path, {agg_col}
        from v
        group by path
        order by 2""".format(agg_col=agg_columns[agg_column])

        c['details_query'] = """select mf1.id, mf1.file_name,
            mf1.directory as dir1,
            mf2.directory as dir2
        from djmediastreamer_mediafile mf1
            inner join djmediastreamer_mediafile mf2 on mf2.id > mf1.id
                and mf1.file_name = mf2.file_name
            left outer join djmediastreamer_directory d on d.path ||
            '/' = substring(mf1.directory || '/', 1, length(d.path) + 1)
        where (mf1.extension = %(extension)s OR %(extension)s is NULL)
            AND (mf1.v_codec = %(video_codec)s OR %(video_codec)s is NULL)
            AND d.path = %(dir)s
        order by mf2.file_name;
        """

        charts['chart_by_repeated'] = c
        return charts

    def get(self, request, *args, **kwargs):
        context = {}
        filters = {f: None for f in StatisticsFiltersForm.declared_fields}
        form = StatisticsFiltersForm(request.GET)
        if form.is_valid():
            for f in filters:
                filters[f] = form.cleaned_data[f] or None
            directory = form.cleaned_data['directory']
            if directory:
                filters['directory'] = directory.path
        charts = []
        agg_column = filters['to_chart'] or 'count'
        for _, c in self.get_chart_definitions(agg_column).items():
            charts.append(plot_query(
                c['query'], c['container'], filters, c['name'],
                agg_column.capitalize())
            )
        context['charts'] = charts
        context['form'] = form
        return render(request, self.template_name, context)
