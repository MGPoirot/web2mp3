from initialize import music_dir, daemon_dir, log_dir, disp_daemons
from utils import Logger, get_url_platform, get_path_components, \
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
    download_info = get_song_db().loc[track_uri]

    # Unpack kwargs from track tags
    idx = download_info.index.str.contains('_kwarg_')
    kwargs = download_info[idx]
    mp3_tags = download_info[~idx]
    kwargs = kwargs.rename({k: k.replace('_kwarg_', '') for k in kwargs.index})

    avoid_duplicates = kwargs.avoid_duplicates
    do_overwrite = kwargs.do_overwrite
    ps = kwargs.print_space
    preferred_quality = kwargs.quality

    # Get path components
    artist_p, album_p, track_p = get_path_components(mp3_tags)

    file_exists = False
    if avoid_duplicates and any(track_exists(artist_p, track_p)):
        logger('Skipped: FileExists')
        file_exists = True
    else:
        # Define paths
        album_dir = os.path.join(music_dir, artist_p, album_p)
        tr_prefix = None if mp3_tags.track_num is None else \
            f'{mp3_tags.track_num} - '
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

        cov_exists = os.path.isfile(cov_fname)
        if cover_url is None:
            logger('ValueError: No cover URL set.')
        elif cov_exists and not do_overwrite:
            logger('FileExistsWarning:'.ljust(ps), f'"{cov_fname}"')
        else:
            if cov_exists:
                logger('File Overwritten:'.ljust(ps), f'"{cov_fname}"')
            download_cover_img(cov_fname, cover_url, logger=logger, print_space=ps)

        # Specify downloading method
        download_method = get_url_platform(track_uri)
        track_url = download_method.uri2url(track_uri)

        # Check if file already exists and if it should be overwritten
        if do_overwrite and os.path.isfile(mp3_fname):
            logger('File Overwritten:'.ljust(ps), f'"{mp3_fname}"')
            os.remove(mp3_fname)

        # Download audio, robust to FileNameTooLongError
        # for i in len(track_p):
        #     short_name = os.path.join(album_dir, f'{tr_prefix}{track_p[:-i]}.mp3')
        #     download_method.audio_download(track_url, short_name, preferred_quality, logger=logger)
        #     if os.path.isfile(short_name): 
        #         break
        # breakpoint()
        
        # Download audio
        download_method.audio_download(track_url, mp3_fname, preferred_quality, logger=logger)


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
            shortdir = restricted_path.replace(str(music_dir), '...')
            try:  # dir not found err
                os.chmod(restricted_path, 0o0777)
                logger('File permissions set for', shortdir)
            except FileNotFoundError as e:
                logger(f'File permissions NOT set for', shortdir, f'\n{e}')
                pass


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
    if verbose:
        if os.name == 'posix':
            # TODO: Fix file access issues on Linus:
            #  I am still getting directory access issues on Linux
            # such that I need to run the code as sudo, and then reset the
            # file permissions to 777. This is not ideal.
            os.system(f'python {__file__} --verbose')
        else:
            os.system(f'python {__file__} --verbose')
    else:
        if os.name == 'posix':
            os.system(f'python {__file__} &')
        else:
            os.system(f'pythonw {__file__}')


def start_daemons(max_daemons=4, verbose=False):
    """
    .. py:function:: start_daemons(max_daemons=4, verbose=False)

    Initiates a number of downloading Daemons.
    Uses the multiprocessing module to initiate a number of daemon processes
    depending on the operating system. If verbose, it will only start one in the
    foreground.

    :param int max_daemons: The number up until new daemons will be started.
    :param bool verbose: Whether to run the daemon process in the foreground

    :return: Number of daemon processes started
    :rtype: int

    :Example:

    >>> start_daemons(max_daemons=4)
    4
    """
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
    """
    .. py:function:: uri2path(uri)

    URI to PATH
    Converts a URI to a path.

    :param str uri: URI of the audio source

    :return: Identifier specified as path
    :rtype: str

    :Example:

    >>> uri2path('youtube:1U2WcqVZhvw')
    'youtube-1U2WcqVZhvw'
    """
    return uri.replace(':', '-')


def uri2tmp(n, uri: str) -> str:
    """ URI to TMP
    Returns a formatted daemon temporary file name as string.
    Temporary files are used to track which file is being worked at

    PARAMETERS:
    :param n    Identifier of the Daemon
    :type n     int or str
    :param uri  URI of the audio source
    :type uri   str

    RETURNS:
    :return: Formatted daemon temporary file name as string

    EXAMPLE:
    >>> uri2tmp('*', 'youtube:y1SHa1AkHkQ')
    '.../.daemons/daemon-*_youtube-1U2WcqVZhvw.tmp'
    """
    return daemon_dir.format(f'{n}_{uri2path(uri)}')


def get_tasks() -> list:
    """ Get tracks to download
    Return a list to tracks to download. Or more explicitly: Return a list of
    track audio sources that have been added to the song database (song_db),
    but for which the download process - and consequently, the setting of its
    song_db entry to None - has not yet been completed.

    PARAMETERS:

    RETURNS:
    :return: Track audo sources as strings
    :rtype:  list

    EXAMPLE:
    >>> get_tasks()
    ['youtube:y1SHa1AkHkQ', 'youtube:y1SHa1AkHkQ']
    """
    #
    # Here 'tasks' means 'tracks that have not been downloaded yet'.
    song_db = get_song_db()
    uris = song_db[song_db.title.notna()].index  # finish
    uris = [u for u in uris if not any(glob(uri2tmp('*', u)))]  # busy
    return uris


@click.command()
@click.version_option()
@click.option("-x", "--max_daemons", default=4,
              help="Number of DAEMONs to spawn as integer")
@click.option("-v", "--verbose", is_flag=True, default=False,
              help="Whether to download in foreground as bool")
@click.option("-c", "--verbose_continuous", is_flag=True, default=False,
              help="When verbose, whether to continue after 1 item")
def daemon_job(max_daemons=4, verbose=False, verbose_continuous=False):
    # List daemons that are not running
    daemon_ns = [i for i in range(max_daemons) if
                 not os.path.isfile(daemon_dir.format(i))]

    if max_daemons == -1:
        # Is it even possible to pass a -1 as flag value in bash?
        # For -1 we always add a daemon
        daemon_ns = [i for i in range(len(glob(daemon_dir.format('*'))) + 1) if
                     not os.path.isfile(daemon_dir.format(i))]
    
    if len(daemon_ns):
        daemon_n = daemon_ns[0]  # Get the first DAEMON that is not running
    else:
        if max_daemons != -1:
            if verbose:
                print('No Daemon initiated, all Daemons are already running:')
                disp_daemons()
                print('Run initialize.py if you want the clean these up.')
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
            task_tmp = Logger(uri2tmp(daemon_n, task))
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
