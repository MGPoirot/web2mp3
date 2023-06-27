from initialize import cookie_file
from utils import hms2s
from youtubesearchpython import VideosSearch
import os
import yt_dlp
import pandas as pd
import pytube

name = 'youtube'
target = 'track'

# Identifier substrings should be defined strictly enough that a URL from
# this platform can never contain this substring without being of this type.
playlist_identifier = '/playlist?'
album_identifier = ' '  # YouTube does not have album object types

playlist_handler = pytube.Playlist
album_handler = lambda album_url: _


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


def get_description(track_url: str, logger=print, market=None) -> str:
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
    # Get video title
    # TODO: replace video search with get page title, since
    # TODO: VideosSearch sometimes returns unexpected results:
    # TODO: https://www.youtube.com/watch?v=qhD3jKUXlGU&ab_channel=Vexento

    yt_search_result = VideosSearch(track_url, limit=1).result()
    if not any(yt_search_result['result']):
        logger(f'ValueError: No video found for "{track_url}"')
        return None
    else:
        yt_search_result = yt_search_result['result'][0]
    youtube_duration = hms2s(yt_search_result['duration'])
    video_title = yt_search_result['title']
    uploader_id = yt_search_result['channel']['name']
    if uploader_id not in video_title:
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
        'cookiefile': cookie_file,
    }
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
    res = [hms2s(i['duration']) / query_duration for i in items]
    return res
