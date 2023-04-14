from utils import print_space, input_is, Logger, hms2s, settings
from settings import print_space
from youtubesearchpython import VideosSearch
import os
import sys
import yt_dlp
import pandas as pd

def get_description(track_url: str, logger: Logger) -> str:
    """
    Receives the link to a YouTube or YouTube Music video and returns the title
    :param logger:
    :param youtube_url: URL as string
    :logger logging object:
    :return: title as string
    """
    # Get video title
    yt_search_result = VideosSearch(track_url, limit=1).result()
    if not any(yt_search_result['result']):
        logger(f'ValueError: No video found for "{track_url}"', verbose=True)
        return None
    else:
        yt_search_result = yt_search_result['result'][0]
    youtube_duration = hms2s(yt_search_result['duration'])
    video_title = yt_search_result['title']
    uploader_id = yt_search_result['channel']['name']
    if uploader_id not in video_title:
        video_title += f' - {uploader_id}'
    description = pd.Series([video_title, youtube_duration], ['video_title', 'duration'])
    return description


def audio_download(youtube_url: str, audio_fname: str, logger=print):
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
        if input_is('No', input('>> Debug? [Yes]/No'.ljust(print_space)) or 'Yes'):
            sys.exit()
        else:
            ydl_opts['verbose'] = True
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
