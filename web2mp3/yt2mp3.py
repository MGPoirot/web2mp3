from utils import rm_char, data_dir, print_space, free_folder, input_is
from song_db import get_song_db, set_song_db
from tag_manager import set_file_tags, download_cover_img
import os
from glob import glob
import sys
import yt_dlp


def yt_download(youtube_url: str, logger=print):
    """
    This handles downloading audio from YouTube and setting the right mp3 tags.
    :param youtube_url:
    :param logger:
    :return: Does not return anything
    """
    # Retrieve and extract song properties from the song database
    mp3_tags = get_song_db()[youtube_url]
    artist_p, album_p, track_p = [rm_char(f) for f in (mp3_tags.album_artist, mp3_tags.album, mp3_tags.title)]

    # Check if this song is already available, maybe in a different album
    existing_tracks = glob(os.path.join(data_dir, '../../Music', artist_p, '*', f'*{track_p}.mp3'))
    if any(existing_tracks):
        logger('FileExistsWarning:')
        for et in existing_tracks:
            logger(''.ljust(print_space), f'{et[len(data_dir) + 5:]}')
    else:
        # Define paths        
        album_dir = os.path.join(data_dir, '../../Music', artist_p, album_p)
        artist_dir = os.path.dirname(album_dir)
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

        # Download audio
        if not os.path.isfile(mp3_fname):
            yt_audio_download(youtube_url, mp3_fname, logger=logger)
        else:
            logger('FileExistsWarning', mp3_fname)

        # Set file tags
        set_file_tags(mp3_tags, mp3_fname, audio_source_url=youtube_url, logger=logger)

        # Fix directory ownership
        free_folder(artist_dir, logger=logger)
        logger('main.py finished successfully')

    set_song_db(youtube_url, None)
    logger('Song data base value cleared to None.')


def yt_audio_download(youtube_url: str, audio_fname: str, logger=print):
    # ydl does not need the extension
    fname, codec = audio_fname.split(os.extsep)

    # Configure download settings
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': codec,
            'preferredquality': '192',
        }],
        'outtmpl': fname,
    }

    # Attempt download
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
    except:
        logger('Something went wrong')
        if input_is('No', input('>> Debug? [Yes]/No'.ljust(print_space)) or 'Yes'):
            logger.close()
            sys.exit()
        else:
            ydl_opts['verbose'] = True
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
