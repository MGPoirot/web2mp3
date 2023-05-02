from initialize import spotify_api
from utils import input_is, flatten, timeout_handler
import pandas as pd
from datetime import datetime
import eyed3
import requests
import shutil


def get_tags_uri(track_tags: pd.Series) -> str:
    return track_tags.internet_radio_url.replace(':track', '')


def get_track_tags(track_item: dict, do_light=False) -> pd.Series:
    # in do_light mode we only get title, album and artist information;
    # just enough to do matching.
    read_timeout = False
    album = track_item['album']
    tag_dict = {
        'title': track_item['name'],
        'album': album['name'],
        'album_artist': album['artists'][0]['name'],
        'duration': track_item['duration_ms'] / 1000,
    }
    if not do_light:
        features = timeout_handler(spotify_api.audio_features, track_item['uri'])[0]
        if features is not None:
            # Disc information
            total_discs = spotify_api.album_tracks(
                album_id=album['uri'],
                offset=album['total_tracks'] - 1,
            )['items'][-1]['disc_number']
            disc_no = (track_item['disc_number'], total_discs)

            # Track number information
            track_no = (track_item['track_number'], album['total_tracks'])

            # Artists information
            artist_items = track_item['artists']
            artists = '; '.join([a['name'] for a in artist_items])

            # Genre information
            genres = [spotify_api.artist(a['uri'])['genres'] for a in
                      artist_items]
            genres = '; '.join(flatten(genres))
            cover_img = album['images'][0]['url'] if any(album['images']) else None

            tag_dict.update({
                'bpm': int(features['tempo']),
                'artist': artists,
                'internet_radio_url': track_item['uri'],
                'cover': cover_img,
                'disc_num': disc_no,
                'genre': genres,
                'release_date': album['release_date'],
                'recording_date': album['release_date'],
                'tagging_date': datetime.now().strftime('%Y-%m-%d'),
                'track_num': track_no,
            })
    tag_series = pd.Series(tag_dict)
    return tag_series


def manual_track_tags(market='NL') -> pd.Series:
    tag_dict = {
        'album': input('>>> Album name?'.ljust(print_space)) or None,
        'album_artist': input('>>> Artist name?'.ljust(print_space)),
        'artist': None,
        'internet_radio_url': 'manual',
        'cover': input('>>> Cover URL?'.ljust(print_space)) or None,
        'disc_num': 1,
        'genre': None,
        'release_date': input('>>> Album year?'.ljust(print_space)) or None,
        'tagging_date': datetime.now().strftime('%Y-%m-%d'),
        'title': input('>>> Track name?'.ljust(print_space)),
        'track_num': input('>>> Track No.?'.ljust(print_space)) or None,
    }
    tag_series = pd.Series(tag_dict)
    tag_series.artist = tag_series.album_artist
    tag_series.recording_date = tag_series.release_date
    if tag_series.album is None:
        tag_series.album = tag_series.title
    found_artist = timeout_handler(spotify_api.search,
                                   q=tag_series.artist,
                                   market=market,
                                   limit=1,
                                   type='artist',
                                   )['artists']['items'][0]
    is_artist = input(f'>>> Is this the artist you were looking for? '
                      f'"{found_artist["name"]}" [Yes]/No') or 'Yes'
    if not input_is('No', is_artist):
        tag_series.artist = found_artist["name"]
        tag_series.genre = ';'.join(found_artist['genres'])
    return tag_series


def set_file_tags(mp3_tags: dict, file_name: str, audio_source_url=None,
                  logger=print):
    # Set mp3 file meta data
    audiofile = eyed3.load(file_name)
    for args in mp3_tags.items():
        audiofile.tag.__setattr__(*args)
    if audio_source_url is not None:
        audiofile.tag.audio_source_url = audio_source_url
        internet_radio_url = mp3_tags['internet_radio_url']
        audiofile.tag.comments.set(
            f'Audio Source: "{audio_source_url},'
            f'Meta Data Source: "{internet_radio_url}",'
        )
    audiofile.tag.save()
    logger('Successfully written file meta data')


def download_cover_img(cover_img_path: str, cover_img_url: str, logger=print):
    """ Downloads an image from a URL and stores at a given path."""
    # Retrieve image
    res = requests.get(cover_img_url, stream=True)
    # Save image
    if res.status_code == 200:
        try:
            with open(cover_img_path, 'wb') as f:
                shutil.copyfileobj(res.raw, f)
            logger('Image Downloaded'.ljust(print_space), f'"{cover_img_path}"')
        except FileNotFoundError as e:
            raise FileNotFoundError(f'This folder was not suitable: "'
                                    f'{cover_img_path}"')
    else:
        raise ConnectionError('Album cover image could not be retrieved.')
