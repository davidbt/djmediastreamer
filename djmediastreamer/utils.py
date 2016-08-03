import re
import subprocess

from .models import Directory


def is_int(string):
    try:
        a = int(string)
        return True
    except:
        return False


def get_allowed_directories(user):
    if user.is_superuser:
        return Directory.objects.filter(ignore=False)
    else:
        return user.directories.filter(ignore=False)


def can_access_directory(user, directory):
    return bool(get_allowed_directories(user).filter(id=directory.id))


def can_access_mediafile(user, mediafile):
    for d in get_allowed_directories(user):
        if mediafile.directory.startswith(d.path):
            return True
    return False


def get_subtitles_from_request(request):
    # TODO: add doc
    subtitles = []
    i = 0
    url = ''
    while request.GET.get('sub_{i}'.format(i=i)):
        k = 'sub_{i}'.format(i=i)
        s = request.GET[k]
        subtitles.append(s)
        url += '&{k}={s}'.format(k=k, s=s)
        i += 1
    return subtitles, url


class MediaInfo(object):
    def __init__(self, file_path):
        self.minfo_output = subprocess.check_output(['mediainfo', file_path])
        self.file_path = file_path

    def search(self, query, lines=None, lower=False):
        if not lines:
            lines = self.minfo_output.split('\n')
        for i, l in enumerate(lines):
            if lower:
                l = l.lower()
            if l.startswith(query):
                if ':' not in l:
                    return i, l
                else:
                    index = l.index(':') + 2
                    return i, l[index:].replace(' ', '')
        return -1, ''

    def get_size(self):
        _, str_w = self.search('Width')
        _, str_h = self.search('Height')
        str_w = str_w.replace('pixels', '')
        str_h = str_h.replace('pixels', '')
        w = int(str_w) if is_int(str_w) else None
        h = int(str_h) if is_int(str_h) else None
        return (w, h)

    def _get_codec(self, codec_type):
        i, _ = self.search(codec_type, lower=True)
        if i >= 0:
            lines = self.minfo_output.split('\n')[i:]
            _, f = self.search('Format', lines=lines)
            if f:
                return f
        return None

    def get_video_codec(self):
        f = self._get_codec('video')
        if f:
            f = f.replace('MPEG-4Visual', 'MPEG-4')
        return f

    def get_audio_codec(self):
        return self._get_codec('audio')

    def parse_duration(self, duration):
        'Returns the file duration in seconds.'
        p = re.compile('([0-9]+h)*([0-9]+mn)*([0-9]+s)*([0-9]+ms)*')
        match = p.findall(duration)
        if match:
            hours = int(match[0][0].replace('h', '') or '0')
            minutes = int(match[0][1].replace('mn', '') or '0')
            seconds = int(match[0][2].replace('s', '') or '0')
            return hours * 3600 + minutes * 60 + seconds
        return None

    def get_duration(self):
        i, _ = self.search('video', lower=True)
        if i >= 0:
            lines = self.minfo_output.split('\n')[i:]
            _, str_d = self.search('Duration', lines=lines)
            d = self.parse_duration(str_d)
            return d

    def get_mkv_subtitles_index(self):
        output = subprocess.check_output(['mkvinfo', self.file_path])
        lines = output.splitlines()
        for i, l in enumerate(lines):
            if 'mero de pista:' in l or 'Track number' in l:
                if lines[i + 2].endswith('subtitles'):
                    return int(l.split(':')[1].strip()[0]) - 1
        return None

    def extract_mkv_subtitles(self, id, index):
        sub_file = 'subtitle_{id}.srt'.format(id=id)
        sub_param = '{index}:{sub_file}'.format(index=index, sub_file=sub_file)
        output = subprocess.check_output(
            ['mkvextract', 'tracks', self.file_path, sub_param]
        )
        return sub_file
