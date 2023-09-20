import pandas as pd







# PSA: strictly define all substring patterns to avoid conflicts
# the name of the module
name = 'soundcloud'

# what the tool can receive from the module
target = 'track'

# patterns to match in a URL
url_patterns = ['soundcloud.com', 'soundcloud:', ]

# substring to recognize a playlist object
playlist_identifier = ' '

# substring to recognize an album object
album_identifier = ' '


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