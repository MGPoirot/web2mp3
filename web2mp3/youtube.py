from utils import print_space, input_is, Logger
from youtubesearchpython import VideosSearch
import os
import sys
import yt_dlp


def url2title(youtube_url: str, logger: Logger) -> str:
    """
    Receives the link to a YouTube or YouTube Music video and returns the title
    :param logger:
    :param youtube_url: URL as string
    :logger logging object:
    :return: title as string
    """
    # Get video title
    yt_search_result = VideosSearch(youtube_url, limit=1).result()
    if not any(yt_search_result['result']):
        logger(f'ValueError: No video found for "{youtube_url}"', verbose=True)
        return None
    video_title = yt_search_result['result'][0]['title']
    uploader_id = yt_search_result['result'][0]['channel']['name']
    if uploader_id not in video_title:
        video_title += f' - {uploader_id}'
    return video_title


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
