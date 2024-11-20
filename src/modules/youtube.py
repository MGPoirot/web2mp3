from initialize import cookie_file
from utils import input_is
from ytmusicapi import YTMusic
import os
import yt_dlp
import pytube
from typing import Tuple, List

# PSA: strictly define all substring patterns to avoid conflicts
# the name of the module
name = 'youtube'

# what the tool can receive from the module
target = 'track'

# substring patterns to match in a URL
url_patterns = ['youtube.com', 'youtu.be', 'youtube.', ]

# substring to recognize a playlist object
playlist_identifier = '/playlist?'

# substring to recognize an album object
album_identifier = ' '  # YouTube does not have album object types

playlist_handler = pytube.Playlist


def url_unshortner(object_url: str) -> str:
    return object_url


def sort_lookup(query: dict, matched_obj: dict | None) -> Tuple[str | None, dict | None]:
    track_uri = url2uri(query['track_url'])
    track_tags = matched_obj
    return track_uri, track_tags


def get_search_platform():
    from modules import spotify
    return spotify


def url2uri(url: str, raw=False) -> str:
    uri = url.split('&')[0].split('watch?v=')[-1].split('?si=')[0].split('.be/')[-1]
    domain = '' if raw else name
    uri = f'{domain}.{uri}'
    if len(uri) != 19:
        raise ValueError(f'Inappropriate URI length "{uri}" constructed from "{url}".')
    return uri


def get_artist(item: dict) -> str:
    return "; ".join([a['name'] for a in item['artists']])


def item2desc(item: dict) -> Tuple[str]:
    return item['title'], get_artist(item)


def uri2url(uri: str) -> str:
    return f'https://www.youtube.com/watch?v={uri.split(".")[-1]}'


def search_yt(query: str, market, limit=1) -> List[dict]:
    """
    This method prioritizes three search strategies:
    1. Top result of all videos
    2. Song videos
    3. Any videos
    """
    yt_search_results = []
    ytmusic = YTMusic(location=market)
    for filter in (None, 'songs', 'videos'):
        results = ytmusic.search(query=query, filter=filter, limit=limit)
        if any(results):
            if filter is None and 'Top result' in [r['category'] for r in results]:
                yt_search_results.extend([r for r in results if r['category'] == 'Top result'])
            else:
                yt_search_results.extend(results)
            if len(yt_search_results) >= limit:
                break
    return yt_search_results[:limit]


def get_description(track_url: str, query: str | None = None, **kwargs) -> dict | None:
    """
    Receives the link to a YouTube or YouTube Music video and returns the title

    Args:
        :param query: what to search YouTube for; defaults to the URL
        :param track_url: URL of the video as string

    Returns:
        :return: key information of the YouTube video as dict
        :rtype: dict or None
    """
    logger = kwargs['logger'] if 'logger' in kwargs else print
    ps = kwargs['print_space'] if 'print_space' in kwargs else 0
    market = kwargs['market']
    if query is None:
        track_url = track_url.split('&')[0]
        track_uri = url2uri(track_url).split('.')[-1] if query is None else query
        meta = YTMusic().get_song(track_uri)['videoDetails']
        query = f'{meta["title"]} {meta["author"]}'
    search_result = search_yt(query, market, limit=1)[0]

    if search_result is None:
        logger(f'ValueError:'.ljust(ps), f'No video found for "{track_url}"')

        # If default response is None we can request input from the user
        if kwargs['response'] is None:
            try_manual = input('How to continue?\n'
                               '1) Manual YouTube [Q]uery\n'
                               '2) Manual track [D]escription\n'
                               '3) [Abort]\n')
        else:
            try_manual = False

        # Act according to answer on how to continue
        if not try_manual or input_is('Abort', try_manual):
            return None
        elif input_is('Query', try_manual) or try_manual == 1:
            new_yt_query = input('Give YouTube Query:  ')
            return get_description(track_url, new_yt_query, **kwargs)
        elif input_is('Description', try_manual) or try_manual == 2:
            search_result = {
                'title': input('Video title?  '),
                'duration_seconds': input('Video duration in seconds?  '),
                'artists': [{'name': input('Artist name?  ')}],
                'album': {'name': input('Album name?  ')},
            }

    # Safely get all parameters
    artist = get_artist(search_result)
    album = search_result['album']['name'] if 'album' in search_result else None
    if 'duration_seconds' in search_result:
        duration = search_result['duration_seconds']
    else:
        duration = int(YTMusic().get_song(track_uri)['videoDetails']['lengthSeconds'])
    # We return a series object that we can use for matching
    description = {'track_url': track_url,
                   'title': search_result['title'],
                   'artist': artist,
                   'album': album,
                   'duration': duration}
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
            print('Cookie file found:', cookie_file)
            ydl_opts.update({'cookiefile': str(cookie_file)})
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


def search(search_query, **kwargs) -> List[dict]:
    return search_yt(
        query=search_query,
        market=kwargs['market'],
        limit=kwargs['search_limit'],
    )


def t_extractor(*items, query_duration=1) -> List[float]:
    # Returns duration of a track from a list of tracks as float
    res = [i['duration_seconds'] if 'duration_seconds' in i else None for i in items]
    res = [i / query_duration if i is not None else None for i in res]
    return res
