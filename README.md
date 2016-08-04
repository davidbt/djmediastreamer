# djmediastreamer
A Django project that allows you to catalog and stream your videos (using FFmpeg to add subtitles and transcode).


## Installation
install postgresql, ffmpeg and mediainfo.


Create djmediastreamer user and database.
```
sudo -u postgres createuser djmediastreamer
sudo -u postgres createdb -O djmediastreamer djmediastreamer
```

configure postgresql security (pg_hba.conf). Something like this:
```host    djmediastreamer             djmediastreamer             127.0.0.1/32            trust
```

Create the python environment.
```cd ~
mkdir djmediastreamer
virtualenv env
source env/bin/activate
```

Clone the repo.
```git clone https://github.com/davidbt/djmediastreamer.git
```

Install the requirements.
```cd djmediastreamer
pip install -r deploy/requirements.txt
```

Run the migrations.
```./manage.py migrate
```

Create a superuser
```./manage.py createsuperuser
```

Run the server
```./manage.py runserver
```

Go to the [admin page] (http://localhost:8000/admin/)
Login, click on directories and the on "ADD DIRECTORY". In path enter the path where your videos are stored, ignore the rest of the fields and save.

Go to the [home page] (http://localhost:8000/). Threre should be a link to your directory but before you can watch you videos you should collect them clicking on "Collect". It should take a few seconds.

Now your are ready to click on your directory, it should show you all the videos in your directory with links to stream or download them.

