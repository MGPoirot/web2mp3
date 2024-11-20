from initialize import spotify_api
from utils import timeout_handler
from tag_manager import get_track_tags
from spotipy.exceptions import SpotifyException
import requests
from typing import Tuple, List

# PSA: strictly define all substring patterns to avoid conflicts
# the name of the module
name = 'spotify'

# what the tool can receive from the module
target = 'tags'

# patterns to match in a URL
url_patterns = ['open.spotify.com', 'spotify.link', 'spotify.', ]

# substring to recognize a playlist object
playlist_identifier = '/playlist/'
album_identifier = '/album/'


def url_unshortner(object_url: str) -> str:
    if 'spotify.link' in object_url:
        r = requests.head(object_url, allow_redirects=True)
        object_url = r.url
    return object_url


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
    try:
        results = timeout_handler(method, uri)['tracks']
    except SpotifyException as e:
        mtd = method.__name__.capitalize()
        if e.http_status == 404:
            print(f'{mtd}NotFound: The object you are looking for is probably '
                  f'private')
        else:
            print(f'Unknown Spotify Error in retrieving {mtd} items')
        return []
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


def sort_lookup(query: dict, matched_obj: dict | None) -> Tuple[str | None, dict | None]:
    # Sorts the mp3 URL and track tags
    track_uri = None if matched_obj is None else matched_obj['track_uri']
    track_tags = query
    return track_uri, track_tags


def get_search_platform():
    # Returns the module that handles the search platform
    from modules import youtube
    return youtube


def item2desc(item: dict) -> Tuple[str]:
    item = get_track_tags(item, do_light=True)
    return item['title'], item['artist']


def get_description(track_url: str, **kwargs) -> dict:
    market = kwargs['market']
    # Gets information about the track that will be used as query for matching
    item = timeout_handler(spotify_api.track, track_url, market=market)
    item['title'] = item.pop('name')
    return get_track_tags(item)


def url2uri(url: str, raw=False) -> str:
    uri = url.split('?')[0].split('/track/')[-1].split('/playlist/')[-1]
    domain = '' if raw else 'spotify.'
    return f'{domain}{uri}'


def uri2url(uri: str) -> str | None:
    return f"https://open.spotify.com/track/{uri.split('.')[-1]}"


def search(search_query, **kwargs) -> List[dict]:
    search_limit = kwargs['search_limit']
    market = kwargs['market']
    results = spotify_api.search(
        q=search_query,
        limit=search_limit,
        market=market,
        type='track'
    )
    items = results['tracks']['items']

    # Rename track name to track title
    for item in items:
        item['title'] = item.pop('name')
    return items


def t_extractor(*items, query_duration=1) -> list:
    # Returns duration of a track from a list of tracks as float
    return [i['duration_ms'] / 1000 / query_duration for i in items]