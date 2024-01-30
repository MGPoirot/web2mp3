from __future__ import annotations

from initialize import cookie_file
from utils import hms2s, input_is
from youtubesearchpython import VideosSearch
import os
import yt_dlp
import pandas as pd
import pytube

# PSA: strictly define all substring patterns to avoid conflicts
# the name of the module
name = 'youtube'

# what the tool can receive from the module
target = 'track'

# substring patterns to match in a URL
url_patterns = ['youtube.com', 'youtu.be', 'youtube:', ]

# substring to recognize a playlist object
playlist_identifier = '/playlist?'

# substring to recognize an album object
album_identifier = ' '  # YouTube does not have album object types

playlist_handler = pytube.Playlist


def url_unshortner(object_url: str) -> str:
    return object_url


def sort_lookup(query: pd.Series, matched_obj: pd.Series):
    track_url = url2uri(query.track_url)
    track_tags = matched_obj
    return track_url, track_tags


def get_search_platform():
    from modules import spotify
    return spotify


def url2uri(url: str, raw=False) -> str:
    uri = url.split('&')[0].split('watch?v=')[-1].split('.be/')[-1]
    domain = '' if raw else 'youtube:'
    return f'{domain}{uri}'


def uri2url(uri: str) -> str:
    return f'https://www.youtube.com/watch?v={uri.split(":")[-1]}'


def get_description(track_url: str, **kwargs) -> str | None:
    """
    Receives the link to a YouTube or YouTube Music video and returns the title

    Args:
        :param logger:
        :type logger: utils.Logger
        :param track_url: URL as string
        :type track_url: str

    Returns:
        :return: title as string
        :rtype: str or None
    """
    logger = kwargs['logger'] if 'logger' in kwargs else print
    ps = kwargs['print_space'] if 'print_space' in kwargs else 0

    # Get video title
    track_url = track_url.split('&')[0]

    yt_search_result = VideosSearch(track_url, limit=1).result()
    if not any(yt_search_result['result']):
        # In normal situations VideosSearch should work just fine.
        # I've seen few occasions where it unexpectedly did not, the following
        # code is a small bypass to this automatic VideosSearch procedure.
        # Note that it may halt downloading (TODO: implement headless)
        logger(f'ValueError:'.ljust(ps), f'No video found for "{track_url}"')
        try_manual = input('How to continue?\n'
                           '1) Manual YouTube [Q]uery\n'
                           '2) Manual track [D]escription\n'
                           '3) [Abort]\n')
        if not try_manual or input_is('Abort', try_manual):
            return None
        elif input_is('Query', try_manual) or try_manual == 1:
            new_yt_query = input('Give YouTube Query:  ')
            yt_search_result = VideosSearch(new_yt_query, limit=1).result()
            if not any(yt_search_result['result']):
                logger(f'ValueError:'.ljust(ps),
                       f'No video found for "{new_yt_query}"')
                return None
        elif input_is('Description', try_manual) or try_manual == 2:
            yt_search_result = {
                'title': input('Video title?'),
                'duration': input('Video duration in mm:ss?  '),
                'channel': {'name': ''},
            }
    else:
        yt_search_result = yt_search_result['result'][0]
    youtube_duration = hms2s(yt_search_result['duration'])
    video_title = yt_search_result['title']
    uploader_id = yt_search_result['channel']['name']
    if uploader_id.lower() not in video_title.lower():
        video_title += f' - {uploader_id}'

    # We return a series object
    description = pd.Series({'track_url': track_url,
                             'video_title': video_title,
                             'duration': youtube_duration})
    return description


def audio_download(youtube_url: str, audio_fname: str, quality:int,
                   logger=print):
    # ydl does not need the extension
    fname, codec = audio_fname.split(os.extsep)

    # Configure download settings
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': codec,
            'preferredquality': quality,
        }],
        'outtmpl': fname,
    }
    if cookie_file:
        if os.path.isfile(cookie_file):
            ydl_opts.update({'cookiefile': cookie_file})
        else:
            logger('Provided cookiefile does noet exist. Ignored.')
    # Attempt download
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
        logger('Youtube download successful')
    except BaseException as e:
        logger(f'Youtube download failed: {e}')
        if not cookie_file:
            logger('Warning: No COOKIE_FILE was found. Without COOKIE_FILE '
                   'file restricted download will fail.')


def search(search_query, **kwargs):
    search_limit = kwargs['search_limit']
    results = VideosSearch(
        query=search_query,
        limit=search_limit
    ).result()
    items = results['result']
    return items


def t_extractor(*items, query_duration=1) -> list:
    # Returns duration of a track from a list of tracks as float
    res = [hms2s(i['duration']) for i in items]
    res = [i / query_duration if i is not None else None for i in res]
    return res
