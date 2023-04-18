from utils import input_is, hms2s, settings
from settings import print_space
from youtubesearchpython import VideosSearch
import os
import sys
import yt_dlp
import pandas as pd
import pytube

name = 'youtube'
target = 'track'
playlist_handler = pytube.Playlist


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


def get_description(track_url: str, logger: object = print, *kwargs) -> str:
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


def audio_download(youtube_url: str, audio_fname: str, logger: object = print):
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
        logger('Youtube download successful')
    except BaseException as e:
        logger(f'Youtube download failed: {e}')
        do_debug = input('>> Debug? [Yes]/No'.ljust(print_space))
        if input_is('No', do_debug or 'Yes'):
            sys.exit()
        else:
            ydl_opts['verbose'] = True
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
