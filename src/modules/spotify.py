from initialize import spotify_api, default_market
from utils import timeout_handler
from tag_manager import get_track_tags
import pandas as pd
from modules import youtube

name = 'spotify'
target = 'tags'

# Identifier substrings should be defined strictly enough that a URL from
# this platform can never contain this substring without being of this type.
playlist_identifier = '/playlist/'
album_identifier = '/album/'


def general_handler(url: str, method) -> list:
    """
    Handles objects containing multiple tracks such as playlists and albums.
    Returns a list of track URLs
    :param url:     Object url
    :type url:      str
    :param method:  Method to call on the spotify_api
    :type method:   function
    :return:
    """
    uri = url2uri(url, raw=True)
    results = timeout_handler(method, uri)['tracks']
    object_items = results['items']
    while results['next']:
        results = spotify_api.next(results)
        object_items.extend(results['items'])
    if 'track' in object_items[0]:
        object_items = [i['track'] for i in object_items]
    object_urls = [uri2url(t['id']) for t in object_items]

    # omit objects that did not have a URL, such as unavailable content
    object_urls = [u for u in object_urls if u is not None]
    return object_urls


def playlist_handler(url: str) -> list:
    # Forwards the playlist method to the general_handle
    return general_handler(url, spotify_api.playlist)


def album_handler(url: str) -> list:
    # Forwards the album method to the general_handle
    return general_handler(url, spotify_api.album)


def sort_lookup(query: pd.Series, matched_obj: pd.Series):
    # Sorts the mp3 URL and track tags
    track_uri = youtube.url2uri(matched_obj.track_url)
    track_tags = query
    return track_uri, track_tags


def get_search_platform():
    # Returns the module that handles the search platform
    from modules import youtube
    return youtube


def get_description(track_url: str, logger, market: str) -> pd.Series:
    # Gets information about the track that will be used as query for matching
    item = timeout_handler(spotify_api.track, track_url, market=market)
    track_tags = get_track_tags(item, do_light=False)
    query = track_tags
    return query


def url2uri(url: str, raw=False) -> str:
    uri = url.split('?')[0].split('/track/')[-1].split('/playlist/')[-1]
    domain = '' if raw else 'spotify:'
    return f'{domain}{uri}'


def uri2url(uri: str) -> str:
    try:
        return f"https://open.spotify.com/track/{uri.split(':')[-1]}"
    except AttributeError:
        # NoneType object has no attribute split
        return None


def search(search_query, **kwargs):
    search_limit = kwargs['search_limit']
    market = kwargs['market']
    results = spotify_api.search(
        q=search_query,
        limit=search_limit,
        market=market,
        type='track'
    )
    items = results['tracks']['items']
    return items


def t_extractor(*items, query_duration=1) -> list:
    # Returns duration of a track from a list of tracks as float
    res = [i['duration_ms'] / 1000 / query_duration for i in items]
    if len(res) == 1:
        res = res[0]
    return res