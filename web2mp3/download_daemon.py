from setup import music_dir, daemon_dir, log_dir, settings
from settings import print_space, max_daemons
import os
from glob import glob
from song_db import get_song_db, set_song_db
from tag_manager import download_cover_img, set_file_tags
from utils import Logger, get_url_domain, shorten_url, get_path_components, track_exists
import youtube
import atexit
import sys
from multiprocessing import Process


def download_track(track_url: str, logger=print):
    """
    This handles downloading audio from YouTube and setting the right mp3 tags.
    :param track_url:
    :param download_method:
    :param logger:
    :return: Does not return anything
    """
    logger('Started download_track')

    # Retrieve and extract song properties from the song database
    mp3_tags = get_song_db()[track_url]
    artist_p, album_p, track_p = get_path_components(mp3_tags)
    if not track_exists(artist_p, track_p):
        # Define paths
        album_dir = os.path.join(music_dir, artist_p, album_p)
        tr_prefix = None if mp3_tags.track_num is None else f'{mp3_tags.track_num} - '
        cov_fname = os.path.join(album_dir, 'folder.jpg')
        mp3_fname = os.path.join(album_dir, f'{tr_prefix}{track_p}.mp3')
        os.makedirs(album_dir, mode=0o777, exist_ok=True)
        get_path_components
        # Log storage locations
        logger('Album dir'.ljust(print_space), album_dir)
        logger('Cover filename    '.ljust(print_space), cov_fname)
        logger('MP3 Audio filename'.ljust(print_space), mp3_fname)

        # Download cover
        if not 'cover' in mp3_tags:
            logger('KeyError: Cover URL was not set at all')
        else:
            cover_url = mp3_tags.pop('cover')
        if os.path.isfile(cov_fname):
            logger('FileExistsWarning:', cov_fname)
        elif cover_url is None:
            logger('ValueError: No cover URL set.')
        else:
            download_cover_img(cov_fname, cover_url, logger=logger)

        # Specify downloading method
        domain = get_url_domain(track_url)
        if domain == 'youtube':
            download_method = youtube
        elif domain == 'soundcloud':
            return
        else:
            return

        # Download audio
        if not os.path.isfile(mp3_fname):
            download_method.audio_download(track_url, mp3_fname, logger=logger)
        else:
            logger('FileExistsWarning', mp3_fname)

        # Set file tags
        set_file_tags(mp3_tags, mp3_fname, audio_source_url=track_url, logger=logger)

        # Potentially fix permissions
        for restricted_path in (album_dir, mp3_fname, cov_fname):
            os.chmod(restricted_path, 0o0777)  # TODO: set proper file permissions! 755
        logger('File permissions set.')
    
    # Clear song_db
    set_song_db(track_url, None)
    logger('Song data base value cleared to None.')

    # Finish
    logger('daemon_download.py finished successfully')


def syscall():
    # believe it or not, this does make a difference compared to
    # - not the call
    # - assigning a lambda function
    if os.name == 'posix':
        os.system(f'python download_daemon.py &')
    else:
        os.system(f'pythonw download_daemon.py')


def start_daemon():
    n_daemons = len(glob(daemon_dir.format('[0-9]')))
    if n_daemons < max_daemons:
        p = Process(target=syscall)
        p.start()
    return


def u2t(n, t: str) -> str: 
    return daemon_dir.format(f'{n}_{shorten_url(t)}')


if __name__ == '__main__':
    daemon_n = len(glob(daemon_dir.format('[0-9]')))
    daemon_tmp = Logger(daemon_dir.format(daemon_n))
    atexit.register(daemon_tmp.rm)
    tried = []
    while True:
        song_db = get_song_db()
        urls = [u for u, tags in song_db.items() if tags is not None]  # finish
        urls = [u for u in urls if not any(glob(u2t('*', u)))]  # busy
        urls = [u for u in urls if not u in tried]  # max tries
        if any(urls):
            task = urls[0]
            tried.append(task)
            task_tmp = Logger(u2t(daemon_n, task))
            atexit.register(task_tmp.rm)
            logger_path = log_dir.format(shorten_url(task))
            sys.stdout = open(logger_path.replace('json', 'txt'), "w")
            log_obj = Logger(logger_path, verbose=True)
            download_track(task, logger=log_obj)
            task_tmp.rm()
        else:
            break

