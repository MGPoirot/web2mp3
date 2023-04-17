from utils import Logger
import pandas as pd

name = 'soundcloud'
target = 'track'


def sort_lookup(query: pd.Series, matched_obj: pd.Series):
    track_url = query.track_url
    track_tags = matched_obj
    return track_url, track_tags



def get_description(soundcloud_url: str, logger: object = print, *kwargs) -> \
        str:
    raise NotImplementedError('Soundcloud API connection has not been implemented yet')

def audio_download(soundcloud_url: str, audio_fname: str, logger: object
 = print):
    return