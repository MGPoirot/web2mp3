import pandas as pd
from utils import spotify, input_is, flatten, settings
from settings import print_space
from datetime import datetime
import eyed3
import requests
import shutil
from time import sleep


def get_track_tags(track_item: dict, logger=print, do_light=False) -> pd.Series:
    # in do_light mode we only get title, album and artist information;
    # just enough to do matching.
    read_timeout = False

    tag_dict = {
        'title': track_item['name'],
        'album': track_item['album']['name'],
        'album_artist': track_item['album']['artists'][0]['name'],
        'duration': track_item['duration_ms'] / 1000,
    }
    if not do_light:
        while True:
            try:
                features = spotify.audio_features(track_item['uri'])[0]
                break
            except KeyboardInterrupt:
                print('KeyboardInterrupt')
                return
            except TimeoutError:
                if not read_timeout:
                    read_timeout = True
                    logger('get_track_tags encountered'
                           ' a SpotiPy API ReadTimeout error')
                    sleep(2)
                else:
                    logger('get_track_tags failed after'
                           ' a SpotiPy API ReadTimeout error')
                    return
        if features is not None:
            artist_items = track_item['artists']
            genres = [spotify.artist(a['uri'])['genres'] for a in artist_items]
            tag_dict.update({
                'bpm': int(features['tempo']),
                'artist': '; '.join([a['name'] for a in artist_items]),
                'internet_radio_url': track_item['uri'],
                'cover': track_item['album']['images'][0]['url'],
                'disc_num': spotify.track(track_item['uri'])['disc_number'],
                'genre': '; '.join(flatten(genres)),
                'release_date': track_item['album']['release_date'],
                'recording_date': track_item['album']['release_date'],
                'tagging_date': datetime.now().strftime('%Y-%m-%d'),
                'track_num': track_item['track_number'],
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
    found_artist = spotify.search(
        q=tag_series.artist,
        market=market,
        limit=1,
        type='artist'
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
            logger('Image Downloaded'.ljust(print_space), cover_img_path)
        except FileNotFoundError:
            raise FileNotFoundError('This folder was not suitable.')
    else:
        raise ConnectionError('Album cover image could not be retrieved.')
