from setup import music_dir, settings
from settings import print_space, max_time_outs
import pickle
import os
import inspect
from datetime import datetime
import eyed3
import json
import sys
import pandas as pd
import re
from glob import iglob
eyed3.log.setLevel("ERROR")
from time import sleep


def hms2s(hhmmss: str) -> int:
    """
    Converts a string representing time in the format "hh:mm:ss" to seconds.

    Args:
        :param hhmmss: The time in the format "hh:mm:ss", "mm:ss" or "ss".
        :type hhmmss: str

    Returns:
        :return: The time in seconds.
        :rtype: int
    """
    components = hhmmss.split(':')
    components.reverse()
    return sum([int(value) * multiplier for value, multiplier in zip(components, (1, 60, 3600))])


def get_url_platform(track_url: str, logger: object = print):
    """
    The function get_url_platform extracts the domain name from a given URL. If a
     known domain is found in the URL, it returns the corresponding domain name
     as a string. Otherwise, it raises a KeyError with a list of known domain
     patterns.

    Args:
        :param logger:
        :type logger:
        :param track_url: The URL string to extract the domain from.
        :type track_url: str

    Returns:
        :return: The extracted domain name string.
        :rtype: str

    Raises:
        :raise KeyError: If the URL does not contain any known domain patterns.

    Example:
        > get_url_platform('http://open.spotify.com/track/0PCM1aBGD8kGJmBizoW2iM')
        'spotify'

        > get_url_platform('https://www.youtube.com/watch?v=NgE5mEQiizQ')
        'youtube'

        > get_url_platform('https://on.soundcloud.com/H4C3V')
        'soundcloud'
    """
    patterns = {'open.spotify.com': 'spotify',
                'youtube.com':      'youtube',
                'soundcloud.com':   'soundcloud',
                'youtu.be':         'youtube',
                'youtube:':         'youtube',
                'spotify:':         'spotify',
                'soundcloud:':      'soundcloud',}
    for pattern, domain in patterns.items():
        if pattern in track_url:
            return domain
    logger(f'No pattern found in "{track_url}".'
           f'Known patterns: {"; ".join(patterns)}')
    return None


def shorten_url(url: str) -> str:
    """
    Shortens a URL by extracting the relevant part from it.

    Args:
        :param url: The URL to be shortened.
        :type url: str

    Returns:
        :return: The shortened URL.
        :rtype: str

    Example:
        > shorten_url(r'https://www.youtube.com/watch?v=z6aONWHhTCU')
        z6aONWHhTCU
    """
    if '=' in url:
        url = url.split('=')[1] if '=' in url else url
    else:
        url = url.split('/')[-1]
    return url.split('&')[0]


class Logger:
    """
    A class for logging information and errors to a file.

    Attributes:
        :attr path: The full path to the log file.
        :type path: str
        :attr verbose: Whether to print log messages to console as well.
        :type verbose: bool
    """
    def __init__(self, full_path=None, verbose=False):
        """
        Initializes the logger.

        Args:
            :param full_path: The full path to the log file.
            :type full_path: str or NoneType
            :param verbose: Whether to print log messages to console as well.
            :type verbose: bool

        Raises:
            :raises OSError: If `full_path` is not a valid path.
        """
        self.path = full_path
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except OSError:
            raise OSError(f'Not a valid path: "{self.path}"')
            sys.exit()
        self.verbose = verbose  # Always print if true

        if not os.path.isfile(self.path):
            json_out({}, self.path)
        self(datetime.now().strftime("%Y-%m-%d %H:%M"))

    def __call__(self, *text, verbose=False):
        """
        Logs the given `text` with the name of the calling function.

        Args:
            :param text: The text to log.
            :param verbose: Whether to print log messages to console as well.

        Returns:
            :return: None
        """
        # Find out who called the logger
        curframe = inspect.currentframe()
        calframe = inspect.getouterframes(curframe, 2)
        caller   = calframe[1][3]

        # See if this caller has recently logged anything
        log_dict = json_in(self.path)
        existing_caller_ids = [k for k in log_dict if caller in k]
        if not any(existing_caller_ids):
            caller_id = f'{str(len(log_dict)).zfill(3)}-{caller}'
            log_dict[caller_id] = []
        else:
            caller_id = existing_caller_ids[-1]

        # Log text
        log_dict[caller_id].append(' '.join(text))
        json_out(log_dict, self.path)
        if verbose or self.verbose:
            print(*text)

    def close(self):
        """
        Writes a closing timestamp to the log file.

        Returns:
            :return: None
        """
        self(datetime.now().strftime("%Y-%m-%d %H:%M"))

    def rm(self):
        """
        Removes the log file from the filesystem.

        Returns:
            :return: None
        """
        if os.path.isfile(self.path):
            os.remove(self.path)


def free_folder(directory: str, owner='pi', logger: object = print):
    # As long as you do not run the command as sudo, you should not end up with ownership issues
    """ Clear any access restrictions and set owner """
    os.system(f"sudo chmod 777 -R '{directory}'")
    os.system(f"sudo chown -R {owner}:{owner} '{directory}'")
    #os.chmod(file, 0o0777)
    #os.chown(file, pwd.getpwnam('plex').pw_uid, )
    logger(f'Rights set to rwxrwsrwx and owner to {owner} for "{directory}"')


def input_is(control: str, input_str: str) -> bool:
    """
    Check if the user input matches either the first letter capitalized or the
     full string.

    Args:
        :param control: The capitalized string to compare against.
        :type control: str
        :param input_str: The input provided by the user.
        :type input_str: str

    Returns:
        :return: True if there is a match, False otherwise.
        :rtype: bool

    Example:
        > input_is('Return', 'R')
        True
        > input_is('Return', 'r')
        True
        > input_is('Return', 'Return')
        True
        > input_is('Return', 'return')
        True
        > input_is('Return', 'Ret')
        False
    """
    return input_str.lower() == control.lower() or input_str.upper() == control[0]


def json_in(source: str):
    """
    Read data from a JSON file and return a dictionary object

    :param source: The path to the JSON file
    :type source: str
    :return: A dictionary object representing the JSON data
    :rtype: dict
    """
    with open(source, 'r') as file:
        return json.load(file)


def json_out(obj: dict, target: str):
    """
    Write dictionary object to a JSON file

    :param obj: The dictionary object to be written
    :type obj: dict
    :param target: The path to the output JSON file
    :type target: str
    """
    with open(target, 'w') as file:
        json.dump(obj, file, indent=4, sort_keys=True)


def pickle_in(source: str) -> dict:
    """
    Read data from a pickle file and return a dictionary object

    :param source: The path to the pickle file
    :type source: str
    :return: A dictionary object representing the pickle data
    :rtype: dict
    """
    with open(source, 'rb') as file:
        return pickle.load(file)


def pickle_out(obj: dict, target: str):
    """
    Write dictionary object to a pickle file

    :param obj: The dictionary object to be written
    :type obj: dict
    :param target: The path to the output pickle file
    :type target: str
    """
    with open(target, 'wb') as file:
        pickle.dump(obj, file)


def flatten(lst: list) -> list:
    """
    Flattens a nested list that contains sub-lists.

    Args:
        :param lst: A nested list.
        :type lst: list

    Returns:
        :return: An unnested list.
        :rtype: list

    Example:
        > nested_list = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        > flatten(nested_list)
        [1, 2, 3, 4, 5, 6, 7, 8, 9]
    """
    return [item for sublist in lst for item in sublist]


def rm_char(text: str) -> str:
    """
    Remove illegal characters from string. This is useful for creating legal
     paths.
    :param text: input string potentially containing illegal characters
    :type text: str
    :return: output string cleaned of illegal characters
    :rtype: str
    """
    for char in '.#%&{}\<>*?/$!":@|`|=\'':
        text = text.replace(char, '')
    return text.strip()


def track_exists(artist_p: str, track_p: str, logger: object = print) -> bool:
    # Check if this song is already available, maybe in a different album
    pattern = re.compile(re.escape(track_p).replace(r'\ ', r'[\s_]*'),
                         re.IGNORECASE | re.UNICODE)
    filenames = iglob(os.path.join(music_dir, artist_p, '*', '*.mp3'))
    existing_tracks = [fn for fn in filenames if pattern.search(fn)]
    if any(existing_tracks):
        logger('FileExistsWarning:')
        for i, et in enumerate(existing_tracks, 1):
            logger(f'   {i})'.rjust(print_space), f'{et[len(music_dir):]}')
    return any(existing_tracks)


def get_path_components(mp3_tags: pd.Series) -> list:
    # Returns the path valid components required to create the file path for
    # storing from a mp3 tags pandas series
    return [rm_char(f) for f in
     (mp3_tags.album_artist, mp3_tags.album, mp3_tags.title)]


def timeout_handler(func, *args, **kwargs):
    """
    The Spotify API might return HTTPSTimeOutErrors, not frequently, but it can
    happen. In these cases, we do not want to give up and call the entire
    matching process quits right away. Instead, we wait for a second and try
    again. This number defines how many times we will reattempt before we give
    up.
    :param func:    Spotify API method to perform
    :param args:    args to func
    :param kwargs:  kwargs to func
    :return:        None
    """
    outcome = None
    n_timeouts = 0
    while outcome is None:
        try:
            outcome = func(*args, **kwargs)
            return outcome
        except TimeoutError:
            n_timeouts += 1
            print(f'Encountered a TimeOutError... '
                  f'waiting {n_timeouts}/{max_time_outs}')
            if n_timeouts > max_time_outs:
                return None
            else:
                sleep(1)




