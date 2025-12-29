from initialize import spotify_api
from utils import input_is, flatten, timeout_handler
from datetime import datetime
import logging
import eyed3
import requests
import shutil
from typing import Dict

eyed3.log.setLevel("ERROR")

# Simple in-process caches to reduce Spotify call volume.
# These are safe because they only memoize immutable Spotify metadata.
_ARTIST_GENRES_CACHE: dict[str, str] = {}
_ALBUM_DISC_MAX_CACHE: dict[str, int] = {}


def get_tags_uri(track_tags: dict) -> str:
    """
    Returns the URI of the source of the tags
    The internet_radio_url field is None when entered manually.
    """
    return track_tags['internet_radio_url'] if 'internet_radio_url' in track_tags else None


def get_track_tags(track_item: dict, do_light: bool = False, logger: logging.Logger | None = None) -> dict:
    # in do_light mode we only get title and artist information;
    # just enough to do matching.

    # Artists information
    artist_items = track_item['artists']
    artists = '; '.join([a['name'] for a in artist_items])

    tag_dict = {
        'title': track_item['title'],
        'artist': artists,
    }
    logger = logger or logging.getLogger(__name__)

    if not do_light:
        album = track_item['album']

        # As of November 27, 2024, Spotify deprecated several Web API endpoints,
        # including those for audio features and audio analysis, citing security concerns.
        # Acquire additional information
        # features = timeout_handler(
        #     func=spotify_api.audio_features,
        #     tracks=track_item['uri'],
        # )[0]
        # if features is not None:
        #     tag_dict.update({'bpm': int(features['tempo']), })

        # Disc information
        disc_num = track_item['disc_number']
        album_uri = album.get('uri')
        if album_uri in _ALBUM_DISC_MAX_CACHE:
            disc_max = _ALBUM_DISC_MAX_CACHE[album_uri]
        else:
            disc_max = timeout_handler(
                func=spotify_api.album_tracks,
                album_id=album_uri,
                offset=album['total_tracks'] - 1,
                _logger=logger,
            )['items'][-1]['disc_number']
            _ALBUM_DISC_MAX_CACHE[album_uri] = disc_max

        # Track number information
        track_num = track_item['track_number']
        track_max = album['total_tracks']

        # Genre information
        genres_list = []
        for a in artist_items:
            a_uri = a.get('uri')
            if not a_uri:
                continue
            if a_uri in _ARTIST_GENRES_CACHE:
                genres_list.append(_ARTIST_GENRES_CACHE[a_uri])
                continue
            g = timeout_handler(
                func=spotify_api.artist,
                artist_id=a_uri,
                _logger=logger,
            ).get('genres', [])
            g_str = '; '.join(g) if isinstance(g, list) else str(g)
            _ARTIST_GENRES_CACHE[a_uri] = g_str
            genres_list.append(g_str)
        genres = '; '.join([g for g in genres_list if g])
        cover_img = album['images'][0]['url'] if any(album['images']) else None
        tags_uri = track_item['uri'].replace('track:', '').replace(':', '.')
        tag_dict.update({
            'album': album['name'],
            'album_artist': artist_items[0]['name'],
            'artist': artists,
            'cover': cover_img,
            'disc_max': disc_max,
            'disc_num': disc_num,
            'duration': track_item['duration_ms'] / 1000,
            'genre': genres,
            'internet_radio_url': tags_uri,
            'release_date': album['release_date'],
            'recording_date': album['release_date'],
            'tagging_date': datetime.now().strftime('%Y-%m-%d'),
            'track_max': track_max,
            'track_num': track_num,
        })
    return tag_dict


def manual_track_tags(market, duration=None, print_space=24) -> dict:
    tag_dict = {
        'album': input('>>> Album name?'.ljust(print_space)) or None,
        'album_artist': input('>>> Artist name?'.ljust(print_space)),
        'artist': None,
        'bpm': None,
        'duration': duration,
        'internet_radio_url': 'manual',
        'cover': input('>>> Cover URL?'.ljust(print_space)) or None,
        'disc_num': input('>>> Disc No.?'.ljust(print_space)) or 1,
        'disc_max': None,
        'genre': None,
        'recording_date': None,
        'release_date': input('>>> Album year?'.ljust(print_space)) or None,
        'tagging_date': datetime.now().strftime('%Y-%m-%d'),
        'title': input('>>> Track name?'.ljust(print_space)),
        'track_num': input('>>> Track No.?'.ljust(print_space)) or 1,
        'track_max': input('>>> No. album tracks?'.ljust(print_space)) or None,
    }

    # Set dependent fields
    for a, b in [('disc_max', 'disc_num'),
                 ('track_max', 'track_num'),
                 ('artist', 'album_artist'),
                 ('recording_date', 'release_date')]:
        tag_dict[a] = tag_dict[b] if tag_dict[a] is None else tag_dict[a]

    tag_series = tag_dict
    if tag_series['album'] is None:
        tag_series['album'] = tag_series.title
    found_artist = timeout_handler(spotify_api.search,
                                   q=tag_series['artist'],
                                   market=market,
                                   limit=1,
                                   type='artist',
                                   )['artists']['items'][0]
    is_artist = input(f'>>> Is this the artist you were looking for? '
                      f'"{found_artist["name"]}" [Yes]/No  ') or 'Yes'
    if not input_is('No', is_artist):
        tag_series['artist'] = found_artist["name"]
        tag_series['genre'] = ';'.join(found_artist['genres'])
    return tag_series


def set_file_tags(mp3_tags: dict, file_name: str, audio_source_url=None,
                  logger: callable = print):
    # Drop None values from tags
    mp3_tags = {k: v for k, v in mp3_tags.items() if v is not None}

    # We can set most track metadata fields directly, but track and disc number
    # are tuples and have to be constructed since JSON cannot store tuples.
    mp3_tags['track_num'] = (mp3_tags['track_num'], mp3_tags.pop('track_max'))
    mp3_tags['disc_num'] = (mp3_tags['disc_num'], mp3_tags.pop('disc_max'))

    # Load the audio file
    logger = logger or logging.getLogger(__name__)

    audiofile = eyed3.load(file_name)

    # Set the track metadata
    for args in mp3_tags.items():
        audiofile.tag.__setattr__(*args)

    # Set some additional fields, logging our tagging process
    if audio_source_url is not None:
        audiofile.tag.audio_source_url = audio_source_url
        internet_radio_url = mp3_tags['internet_radio_url']
        # TODO: why is the internet_radio_url not set when the audio_source_url
        #  is None?
        audiofile.tag.comments.set(
            f'Audio Source: "{audio_source_url},'
            f'Meta Data Source: "{internet_radio_url}",'
        )
    audiofile.tag.save()
    logger.info('Successfully written file meta data')


def download_cover_img(cover_img_path: str, cover_img_url: str, logger: logging.Logger | None = None,
                       print_space=24):
    """ Downloads an image from a URL and stores at a given path."""
    # Retrieve image
    logger = logger or logging.getLogger(__name__)

    # Don't allow this to block forever on a flaky network
    res = requests.get(cover_img_url, stream=True, timeout=15)
    if res.status_code == 429:
        # Let higher-level callers apply Retry-After based backoff
        raise requests.exceptions.HTTPError("HTTP 429", response=res)
    # Save image
    if res.status_code == 200:
        try:
            with open(cover_img_path, 'wb') as f:
                shutil.copyfileobj(res.raw, f)
            logger.info('%s "%s"', 'Image Downloaded'.ljust(print_space), cover_img_path)
        except FileNotFoundError as e:
            raise FileNotFoundError(f'This folder was not suitable: "'
                                    f'{cover_img_path}"')
    else:
        raise ConnectionError('Album cover image could not be retrieved.')


# def get_file_tags(file_name=None, tags=None) -> dict:
#     if tags is None:
#         tags = eyed3.load(file_name).tag
#
#     attributes = (
#         'album', 'album_artist', 'artist', 'bpm', 'duration',
#         'internet_radio_url', 'genre', 'recording_date',
#         'release_date', 'tagging_date', 'title',
#     )
#
#     def _get_attr(attr):
#         try:
#             return tags.__getattribute__(attr)
#         except AttributeError:
#             return None
#     mp3_tags = {a: _get_attr(a) for a in attributes}
#     mp3_tags['disc_num'] = tags.disc_num.count
#     mp3_tags['disc_max'] = tags.disc_num.total
#     mp3_tags['track_num'] = tags.track_num.count
#     mp3_tags['track_max'] = tags.track_num.total
#     return mp3_tags
