from initialize import music_dir, daemon_dir, log_dir, settings
from settings import print_space, max_daemons, verbose, verbose_single, \
    do_overwrite
from utils import Logger, get_url_platform, get_path_components,\
    track_exists, input_is
import os
from glob import glob
from song_db import get_song_db, set_song_db
from tag_manager import download_cover_img, set_file_tags
import atexit
import sys
from multiprocessing import Process
from importlib import import_module


def download_track(track_uri: str, logger=print):
    """
    This handles downloading audio from YouTube and setting the right mp3 tags.
    :param track_uri:
    :param download_method:
    :param logger:
    :return: Does not return anything
    """
    logger('Started download_track')

    # Retrieve and extract song properties from the song database
    mp3_tags = get_song_db().loc[track_uri]
    artist_p, album_p, track_p = get_path_components(mp3_tags)

    file_exists = False
    if track_exists(artist_p, track_p):
        file_exists = True
        logger('Skipped: FileExists')
    else:
        # Define paths
        album_dir = os.path.join(music_dir, artist_p, album_p)
        tr_prefix = None if mp3_tags.track_num is None else\
            f'{mp3_tags.track_num} - '
        cov_fname = os.path.join(album_dir, 'folder.jpg')
        mp3_fname = os.path.join(album_dir, f'{tr_prefix}{track_p}.mp3')
        os.makedirs(album_dir, mode=0o777, exist_ok=True)

        # Log storage locations
        logger('Album dir'.ljust(print_space), f'"{album_dir}"')
        logger('Cover filename    '.ljust(print_space), f'"{cov_fname}"')
        logger('MP3 Audio filename'.ljust(print_space), f'"{mp3_fname}"')

        # Download cover
        if not 'cover' in mp3_tags:
            logger('KeyError: Cover URL was not set at all')
            cover_url = None
        else:
            cover_url = mp3_tags.pop('cover')

        if cover_url is None:
            logger('ValueError: No cover URL set.')
        elif os.path.isfile(cov_fname) and not do_overwrite:
            logger('FileExistsWarning:', cov_fname)
        else:
            if do_overwrite:
                logger('File Overwritten:'.ljust(print_space), f'"{cov_fname}"')
                os.remove(cov_fname)
            download_cover_img(cov_fname, cover_url, logger=logger)

        # Specify downloading method
        domain = get_url_platform(track_uri)
        download_method = import_module(f'modules.{domain}')
        track_url = download_method.uri2url(track_uri)

        # Check if file already exists and if it should be overwritten
        if do_overwrite and os.path.isfile(mp3_fname):
            logger('File Overwritten:'.ljust(print_space), f'"{mp3_fname}"')
            os.remove(mp3_fname)

        # Download audio
        download_method.audio_download(track_url, mp3_fname, logger=logger)

        # Set file tags
        if os.path.isfile(mp3_fname):
            file_exists = True
            set_file_tags(
                mp3_tags=mp3_tags,
                file_name=mp3_fname,
                audio_source_url=track_url,
                logger=logger
            )

        # Potentially fix permissions
        for restricted_path in (album_dir, mp3_fname, cov_fname):
            # TODO: set proper file permissions! 755
            os.chmod(restricted_path, 0o0777)
        logger('File permissions set.')

    # Conclude
    if file_exists:
        set_song_db(track_uri)
        logger('Song data base value cleared to None.')
        conclusion = 'finished successfully.'
    else:
        conclusion = 'failed.'
    logger(f'download_track {conclusion}')


def syscall():
    # Initiates a daemon process depending on the operating system
    if verbose:
        if os.name == 'posix':
            os.system(f'python download_daemon.py verbose')
        else:
            os.system(f'python download_daemon.py verbose')
    else:
        if os.name == 'posix':
            os.system(f'python download_daemon.py background &')
        else:
            os.system(f'pythonw download_daemon.py background')


def start_daemons():
    if verbose:
        syscall()
        return 1

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
    # Converts a uri to a path,
    # eg. 'youtube:1U2WcqVZhvw' -> 'youtube-1U2WcqVZhvw'
    return uri.replace(':', '-')


def u2t(n, uri: str) -> str:
    # Formats a daemon dir temp file name
    return daemon_dir.format(f'{n}_{uri2path(uri)}')


def get_tasks() -> list:
    # List tasks that have not been done and that are not running
    song_db = get_song_db()
    uris = song_db[song_db.title.notna()].index  # finish
    uris = [u for u in uris if not any(glob(u2t('*', u)))]  # busy
    return uris


if __name__ == '__main__':
    """
    Behaviour:
    - Start [default]:  starts daemons until max_daemons has been reached
    - Verbose:          starts one daemon, runs one task and prints logs
    - anything else:    starts one daemon and runs it in the background
    """

    # Accept input
    run_mode = sys.argv[1] if len(sys.argv) > 1 else 'start'
    run_mode = 'verbose' if run_mode == '--mode=client' else run_mode

    # Start daemons
    if input_is('Start', run_mode):
        daemon_started = start_daemons()
        print(f'{daemon_started} Daemons started.')
    else:
        # List daemons that are not running
        daemon_ns = [i for i in range(max_daemons) if not os.path.isfile(
            daemon_dir.format(i))]
        if len(daemon_ns) > 0:
            # Initiate one daemon
            daemon_n = daemon_ns[0]
            daemon_name = daemon_dir.format(daemon_n)
            daemon_tmp = Logger(daemon_name)
            atexit.register(daemon_tmp.rm)
            tried = []
            while True:
                # List tasks that are not running
                uris = get_tasks()
                uris = [u for u in uris if not u in tried]  # max tries
                if len(uris) > 0:
                    # Initiate one task
                    task = uris[0]
                    tried.append(task)
                    task_tmp = Logger(u2t(daemon_n, task))
                    atexit.register(task_tmp.rm)
                    logger_path = log_dir.format(uri2path(task))
                    # Redirect stdout to log file if not verbose
                    if not input_is('Verbose', run_mode):
                        sys.stdout = open(logger_path.replace('json', 'txt'), "w")
                    log_obj = Logger(logger_path, verbose=True)
                    download_track(task, logger=log_obj)
                    task_tmp.rm()
                else:
                    print('No unprocessed URIs found.')
                    break
                if verbose_single and verbose:
                    break
