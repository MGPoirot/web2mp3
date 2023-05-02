from initialize import music_dir, daemon_dir, log_dir
from utils import Logger, get_url_platform, get_path_components,\
    track_exists
import os
from glob import glob
from song_db import get_song_db, set_song_db
from tag_manager import download_cover_img, set_file_tags
import atexit
import sys
from multiprocessing import Process
import click


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
    series = get_song_db().loc[track_uri]

    # Unpack kwargs from track tags
    idx = series.index.str.contains('kwarg')
    kwargs = series[idx]
    mp3_tags = series[~idx]
    kwargs = kwargs.rename({k: k.replace('kwarg_', '') for k in kwargs.index})

    ps = kwargs.print_space
    do_overwrite = kwargs.do_overwrite
    preferred_quality = kwargs.quality
    artist_p, album_p, track_p = get_path_components(mp3_tags)

    file_exists = False
    if track_exists(artist_p, track_p):
        file_exists = True
        logger('Skipped: FileExists')
    else:
        # Define paths
        album_dir = os.path.join(music_dir, artist_p, album_p)
        tr_prefix = None if mp3_tags.track_num is None else\
            f'{mp3_tags.track_num[0]} - '
        cov_fname = os.path.join(album_dir, 'folder.jpg')
        mp3_fname = os.path.join(album_dir, f'{tr_prefix}{track_p}.mp3')
        os.makedirs(album_dir, mode=0o777, exist_ok=True)

        # Log storage locations
        logger('Album dir'.ljust(ps), f'"{album_dir}"')
        logger('Cover filename    '.ljust(ps), f'"{cov_fname}"')
        logger('MP3 Audio filename'.ljust(ps), f'"{mp3_fname}"')

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
                logger('File Overwritten:'.ljust(ps), f'"{cov_fname}"')
                os.remove(cov_fname)
            download_cover_img(cov_fname, cover_url, logger=logger)

        # Specify downloading method
        download_method = get_url_platform(track_uri)
        track_url = download_method.uri2url(track_uri)

        # Check if file already exists and if it should be overwritten
        if do_overwrite and os.path.isfile(mp3_fname):
            logger('File Overwritten:'.ljust(ps), f'"{mp3_fname}"')
            os.remove(mp3_fname)

        # Download audio
        download_method.audio_download(track_url, mp3_fname, quality,
                                       logger=logger)

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


def syscall(verbose=False):
    # Initiates a daemon process depending on the operating system
    __file__
    if verbose:
        if os.name == 'posix':
            os.system(f'python {__file__} --verbose')
        else:
            os.system(f'python {__file__} --verbose')
    else:
        if os.name == 'posix':
            os.system(f'python {__file__} &')
        else:
            os.system(f'pythonw {__file__}')


def start_daemons(max_daemons=4, verbose=False):
    if verbose:
        syscall(verbose)
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


@click.command()
@click.version_option()
@click.option("-x", "--max_daemons", default=-1,
              help="Number of DAEMONs to spawn as integer")
@click.option("-v", "--verbose", is_flag=True, default=False,
              help="Whether to download in foreground as bool")
@click.option("-s", "--verbose_continuous", is_flag=True, default=False,
              help="When verbose, whether to continue after 1 item")
def daemon_job(max_daemons=-1, verbose=False, verbose_continuous=False):
    # List daemons that are not running
    daemon_ns = [i for i in range(max_daemons) if
                 not os.path.isfile(daemon_dir.format(i))]

    if len(daemon_ns):
        daemon_n = daemon_ns[0]  # Get the first DAEMON that is not running
    else:
        if max_daemons != -1:
            return  # Return if all Daemons are running
        # Always initiate the next daemon
        all_daemon_files = range(len(glob(daemon_dir.format('*'))))
        daemons = [i for i in all_daemon_files if
                   os.path.isfile(daemon_dir.format(i))]
        daemon_n = daemons[-1] + 1

    # Initiate the DAEMON
    daemon_name = daemon_dir.format(daemon_n)
    daemon_tmp = Logger(daemon_name)
    atexit.register(daemon_tmp.rm)

    # Go through tasks
    tried = []
    while True:
        # List tasks that are not running
        uris = get_tasks()
        uris = [u for u in uris if u not in tried]  # max tries
        if len(uris) > 0:
            # Initiate one task
            task = uris[0]
            tried.append(task)
            task_tmp = Logger(u2t(daemon_n, task))
            atexit.register(task_tmp.rm)
            logger_path = log_dir.format(uri2path(task))

            # Redirect stdout to log file if not verbose
            if not verbose:
                sys.stdout = open(logger_path.replace('json', 'txt'), "w")
            log_obj = Logger(logger_path, verbose=True)
            download_track(task, logger=log_obj)
            task_tmp.rm()
        else:
            print('daemon_job finished: No unprocessed URIs found.')
            break
        if not verbose_continuous and verbose:
            break


if __name__ == '__main__':
    daemon_job()
