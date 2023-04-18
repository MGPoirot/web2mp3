from setup import music_dir, daemon_dir, log_dir
from settings import print_space, max_daemons
import os
from glob import glob
from song_db import get_song_db, set_song_db
from tag_manager import download_cover_img, set_file_tags
from utils import Logger, get_url_platform, get_path_components,\
    track_exists, input_is
import atexit
import sys
from multiprocessing import Process
from importlib import import_module


def download_track(track_uri: str, logger=print):
    """
    This handles downloading audio from YouTube and setting the right mp3 tags.
    :param track_url:
    :param download_method:
    :param logger:
    :return: Does not return anything
    """
    logger('Started download_track')

    # Retrieve and extract song properties from the song database
    mp3_tags = get_song_db().loc[track_uri]
    artist_p, album_p, track_p = get_path_components(mp3_tags)
    if not track_exists(artist_p, track_p):
        # Define paths
        album_dir = os.path.join(music_dir, artist_p, album_p)
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

        if cover_url is None:
            logger('ValueError: No cover URL set.')
        elif os.path.isfile(cov_fname):
            logger('FileExistsWarning:', cov_fname)
        else:
            download_cover_img(cov_fname, cover_url, logger=logger)

        # Specify downloading method
        domain = get_url_platform(track_uri)
        download_method = import_module(f'modules.{domain}')
        track_url = download_method.uri2url(track_uri)

        # Download audio
        download_method.audio_download(track_url, mp3_fname, logger=logger)

        # Set file tags
        set_file_tags(mp3_tags, mp3_fname, audio_source_url=track_url, logger=logger)

        # Potentially fix permissions
        for restricted_path in (album_dir, mp3_fname, cov_fname):
            os.chmod(restricted_path, 0o0777)  # TODO: set proper file permissions! 755
        logger('File permissions set.')
    
    # Clear song_db
    set_song_db(track_uri)
    logger('Song data base value cleared to None.')

    # Finish
    logger('daemon_download.py finished successfully')


def syscall():
    if os.name == 'posix':
        os.system('python download_daemon.py background &')
    else:
        os.system('pythonw download_daemon.py background')


def start_daemons():
    n_started = 0
    for i, _ in zip(range(max_daemons), get_tasks()):
        n_daemons = len(glob(daemon_dir.format('[0-9]')))
        if n_daemons < max_daemons:
            n_started += 1
            p = Process(target=syscall)
            p.start()
        else:
            break
    return n_started


def uri2path(uri: str) -> str:
    return uri.replace(':', '-')


def u2t(n, uri: str) -> str:
    return daemon_dir.format(f'{n}_{uri2path(uri)}')


def get_tasks() -> list:
    song_db = get_song_db()
    uris = song_db[song_db.title.notna()].index  # finish
    uris = [u for u in uris if not any(glob(u2t('*', u)))]  # busy
    return uris


if __name__ == '__main__':
    # Accept input
    run_mode = sys.argv[1] if len(sys.argv) > 1 else 'start'
    run_mode = 'verbose' if run_mode == '--mode=client' else run_mode

    # Start daemon
    if input_is('Start', run_mode):
        daemon_started = start_daemons()
        print(f'{daemon_started} Daemons started.')
    else:  # Run Daemon (special case is process_mode == verbose)
        daemon_n = len(glob(daemon_dir.format('[0-9]')))
        daemon_name = daemon_dir.format(daemon_n)
        if not os.path.isfile(daemon_name):
            daemon_tmp = Logger(daemon_name)
            atexit.register(daemon_tmp.rm)
            tried = []
            while True:
                uris = get_tasks()
                uris = [u for u in uris if not u in tried]  # max tries
                if any(uris):
                    task = uris[0]
                    tried.append(task)
                    task_tmp = Logger(u2t(daemon_n, task))
                    atexit.register(task_tmp.rm)
                    logger_path = log_dir.format(uri2path(task))
                    if not input_is('Verbose', run_mode):
                        sys.stdout = open(logger_path.replace('json', 'txt'), "w")
                    log_obj = Logger(logger_path, verbose=True)
                    download_track(task, logger=log_obj)
                    task_tmp.rm()
                else:
                    print('No unprocessed URIs found.')
                    break
                if input_is('Verbose', run_mode):
                    break
