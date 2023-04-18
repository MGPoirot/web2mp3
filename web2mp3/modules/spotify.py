from utils import timeout_handler
from setup import spotify_api
from tag_manager import get_track_tags
import pandas as pd
from modules import youtube

name = 'spotify'
target = 'tags'


def playlist_handler(url: str) -> list:
    pl_uri = url2uri(url, raw=True)
    playlist_items = []
    results = timeout_handler(spotify_api.playlist, pl_uri)['tracks']
    while results['next']:
        results = spotify_api.next(results)
        playlist_items.extend(results['items'])
    playlist_urls = [uri2url(t['track']['id']) for t in playlist_items]
    return playlist_urls


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
