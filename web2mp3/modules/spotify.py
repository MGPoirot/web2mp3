from setup import spotify_api
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


def general_handler(url, method):
    uri = url2uri(url, raw=True)
    results = timeout_handler(method, uri)['tracks']
    object_items = results['items']
    while results['next']:
        results = spotify_api.next(results)
        object_items.extend(results['items'])
    if 'track' in object_items[0]:
        object_items = [i['track'] for i in object_items]
    object_urls = [uri2url(t['id']) for t in object_items]
    return object_urls


def playlist_handler(url: str) -> list:
    return general_handler(url, spotify_api.playlist)


def album_handler(url: str) -> list:
    return general_handler(url, spotify_api.album)


def sort_lookup(query: pd.Series, matched_obj: pd.Series):
    track_uri = youtube.url2uri(matched_obj.track_url)
    track_tags = query
    return track_uri, track_tags


def get_search_platform():
    from modules import youtube
    return youtube


def get_description(track_url, logger, market='NL'):
    item = timeout_handler(spotify_api.track, track_url, market=market)
    track_tags = get_track_tags(item, logger=logger, do_light=False)
    query = track_tags
    return query


def url2uri(url: str, raw=False) -> str:
    uri = url.split('?')[0].split('/track/')[-1].split('/playlist/')[-1]
    domain = '' if raw else 'spotify:'
    return f'{domain}{uri}'


def uri2url(uri: str) -> str:
    return f"https://open.spotify.com/track/{uri.split(':')[-1]}"
