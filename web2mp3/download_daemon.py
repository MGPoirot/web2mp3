import os
from glob import glob
from song_db import get_song_db, set_song_db
from tag_manager import download_cover_img, set_file_tags
from utils import Logger, print_space, data_dir, rm_char, daemon_dir, get_url_domain, log_dir, shorten_url, max_daemons
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
    # Retrieve and extract song properties from the song database
    mp3_tags = get_song_db()[track_url]
    artist_p, album_p, track_p = [rm_char(f) for f in (mp3_tags.album_artist, mp3_tags.album, mp3_tags.title)]

    # Check if this song is already available, maybe in a different album
    existing_tracks = glob(os.path.join(data_dir, 'Music', artist_p, '*', f'*{track_p}.mp3'))
    if any(existing_tracks):
        logger('FileExistsWarning:')
        for et in existing_tracks:
            logger(''.ljust(print_space), f'{et[len(data_dir) + 5:]}')
    else:
        # Define paths
        album_dir = os.path.join(data_dir, 'Music', artist_p, album_p)
        tr_prefix = None if mp3_tags.track_num is None else f'{mp3_tags.track_num} - '
        cov_fname = os.path.join(album_dir, 'folder.jpg')
        mp3_fname = os.path.join(album_dir, f'{tr_prefix}{track_p}.mp3')
        os.makedirs(album_dir, mode=0o777, exist_ok=True)

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
            pass

        # Download audio
        if not os.path.isfile(mp3_fname):
            download_method.audio_download(track_url, mp3_fname, logger=logger)
        else:
            logger('FileExistsWarning', mp3_fname)

        # Set file tags
        set_file_tags(mp3_tags, mp3_fname, audio_source_url=track_url, logger=logger)

        # Finish
        logger('main.py finished successfully')

    set_song_db(track_url, None)
    logger('Song data base value cleared to None.')


def syscall():
    # believe it or not, this does make a difference compared to
    # - not the call
    # - assigning a lambda function
    os.system(f'pythonw download_daemon.py &')


def start_daemon():
    n_daemons = len(glob(daemon_dir.format('[0-9]')))
    if n_daemons < max_daemons:
        p = Process(target=syscall)
        p.start()
    return


def u2t(t: str) -> str:
    return daemon_dir.format(f'{daemon_n}_{shorten_url(t)}')


if __name__ == '__main__':
    daemon_n = len(glob(daemon_dir.format('[0-9]')))
    daemon_tmp = Logger(daemon_dir.format(daemon_n))
    atexit.register(daemon_tmp.rm)

    tried = []
    while True:
        song_db = get_song_db()
        daemon_files = glob(daemon_dir.format('*'))
        urls = [u for u, tags in song_db.items() if tags is not None]  # exclude finished
        urls = [u for u in urls if not any([u2t(d) in d for d in daemon_files])]  # exclude busy
        urls = [u for u in urls if not u in tried]  # prevent potential inf while
        if any(urls):
            task = urls[0]
            tried.append(task)
            task_tmp = Logger(u2t(task))
            atexit.register(task_tmp.rm)
            logger_path = log_dir.format(shorten_url(task))
            sys.stdout = open(logger_path.replace('json', 'txt'), "w")
            log_obj = Logger(logger_path, verbose=True)
            download_track(task, logger=log_obj)
            task_tmp.rm()
        else:
            break

