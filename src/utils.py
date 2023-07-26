from initialize import music_dir
import pickle
import os
import inspect
from datetime import datetime
import json
import sys
import pandas as pd
import re
from glob import iglob
from time import sleep
from importlib import import_module
from json.decoder import JSONDecodeError
from collections.abc import Iterable

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
    if hhmmss is None:
        return None
    elif isinstance(hhmmss, int):
        return hhmmss
    elif isinstance(hhmmss, str):
        components = hhmmss.split(':')
        components.reverse()
        return sum([int(value) * multiplier for value, multiplier in
                    zip(components, (1, 60, 3600))])
    else:
        raise NotImplementedError



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
        :return: The extracted domain name module.
        :rtype: module

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
                'youtube.com': 'youtube',
                'soundcloud.com': 'soundcloud',
                'youtu.be': 'youtube',
                'youtube:': 'youtube',
                'spotify:': 'spotify',
                'soundcloud:': 'soundcloud', }
    for pattern, domain in patterns.items():
        if pattern in track_url:
            # Identify the platform where the URL is from
            try:
                module = import_module(f'modules.{domain}')
            except ModuleNotFoundError:
                return
            return module
    logger(f'No pattern found in "{track_url}". '
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
        The special thing about this logging function is that function output
        will be sorted by the function that called it automatically in a dict
        format.

        Args:
            :param text: The text to log.
            :param verbose: Whether to print log messages to console as well.

        Returns:
            :return: None
        """
        # Find out who called the logger
        curframe = inspect.currentframe()
        calframe = inspect.getouterframes(curframe, 2)
        caller = calframe[1][3]

        # See if this caller has recently logged anything
        log_dict = json_in(self.path)
        if not isinstance(log_dict, Iterable):
            log_dict = {'Unassigned': log_dict}
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
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass


def free_folder(directory: str, owner='pi', logger: object = print):
    # As long as you do not run the command as sudo,
    # you should not end up with ownership issues
    """ Clear any access restrictions and set owner """
    os.system(f"sudo chmod 777 -R '{directory}'")
    os.system(f"sudo chown -R {owner}:{owner} '{directory}'")
    # os.chmod(file, 0o0777)
    # os.chown(file, pwd.getpwnam('plex').pw_uid, )
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
    return input_str.lower() == control.lower() or input_str.upper() == control[
        0]


def in_wrapper(module):
    name = module.__name__

    def in_method(source_path: str):
        """
        Read data from a JSON file and return a dictionary object
    
        :param source_path: The path to the JSON file
        :type source_path: str
        :return: A dictionary object representing the JSON data
        :rtype: dict
        """

        def read(mode=''):
            with open(source_path, f'r{mode}') as file:
                return module.load(file)
        try:
            try:
                return read()
            except TypeError:
                return read(mode='b')
        except JSONDecodeError as e:
            print(f'Warning: Issues with loading {name} file "{source_path}".')
            with open(source_path, f'r') as file:
                content = file.read()
            if e.msg == 'Extra data':
                print(f'Warning: Extra data found in the {name} file. ')
                # Split raw data
                junk = '{'.join(content.split('{')[:-1])
                junk = junk[:junk.rfind(',')]
                rest = '{' + content.split('{')[-1]
                # Load
                junk_json = json.loads(junk)
                rest_json = json.loads(rest)
                # Save new files
                new_junk_file = unique_fname(source_path)
                json_out(junk_json, new_junk_file)
                print(f'New file created: "{new_junk_file}"')
                json_out(rest_json, source_path)
                print(f'Data recovered and saved to: "{source_path}"')
                return rest_json
            else:
                print('Error: Recovery failed. No solution to the following '
                      'data issue has been implemented:')
                print(e)
        except FileNotFoundError:
            print("Error: File not found.")
    return in_method


def out_wrapper(module, **kwargs):

    def out_method(obj: dict, target_path: str):
        """
        Write dictionary object to a JSON file

        :param obj: The dictionary object to be written
        :type obj: dict
        :param target: The path to the output JSON file
        :type target: str
        """
        def write(mode=''):
            with open(target_path, f'w{mode}') as file:
                module.dump(obj, file, **kwargs)
        try:
            write()
        except TypeError as e:
            write(mode='b')
    return out_method


json_in = in_wrapper(json)
json_out = out_wrapper(json, indent=4, sort_keys=True)
pickle_in = in_wrapper(pickle)
pickle_out = out_wrapper(pickle)


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
    if text is None:
        return 'NONE'
    for char in '~.#%&{}[]\<>*?/$!":@|`|=\'':
        text = text.replace(char, '')
    return text.strip()


def sanitize_track_name(track_name: str) -> str:
    """Removes common words and phrases from a given track name and returns a
    sanitized string in lower case.

    Args:
        :param track_name: A string representing the original track name.
        :type track_name: str

    Returns:
        :return A string representing the sanitized track name.
        :rtype str

    This function removes the following words and phrases from the track name:
    remastered, remaster, single, special, radio, "- edit", "(stereo)"
    And the following if they appear after any of the above words:
    - version, edit, mix
    Additionally, any 4-digit year preceeding or following above words is
    removed from string.

    Example:
    > sanitize_track_name("Bohemian Rhapsody - Remastered 2011")
    "Bohemian Rhapsody"
    """
    # Define words to remove and second words to remove if they appear after
    words_to_remove = ['remastered', 'remaster', 'single', 'special', 'radio',
                       '- edit', 'stereo', 'digital']
    second_words = [' version', ' edit', ' mix', 'remaster', '']
    track_name = track_name.lower()

    # Define a pattern for any 4-digit year preceeding or following above words
    year_pattern = re.compile(r'(19|20)\d{2}\b', flags=re.IGNORECASE)

    # Perform the removal
    for w1 in words_to_remove:
        for w2 in second_words:
            pattern = f'{w1}{w2}\s*{year_pattern.pattern}|\s*{w1}{w2}'
            track_name = re.sub(pattern, '', track_name)
    track_name = re.sub(year_pattern, '', track_name)

    # Remove any leading or trailing spaces
    track_name = track_name.strip()
    return track_name


def track_exists(artist_p: str, track_p: str, logger=print) -> bool:
    """
    Check if this song is already available, maybe in a different album

    NB: that unlike the matching process in the main function, here we do
    not sanitize track name, removing items like (2018 remaster).

    :param artist_p: artist directory path as string
    :param track_p:  track directory path as string
    :param logger:   logging object
    :param print_space:   spacing of spaces
    :return:
    """

    pattern = re.compile(re.escape(track_p).replace(r'\ ', r'[\s_]*'),
                         re.IGNORECASE | re.UNICODE)
    filepaths = iglob(os.path.join(music_dir, artist_p, '*', '*.mp3'))
    filenames = [os.path.basename(f) for f in filepaths]
    existing_tracks = [fn for fn in filenames if pattern.search(fn)]
    if any(existing_tracks):
        logger(f'FileExistsWarning: {track_p} - {artist_p}\n ',
               *[f'{" " * 3}{i}){" " * 3}'
                 f'{f.split(os.extsep)[0]}\n '
                 for i, f in enumerate(existing_tracks, 1)])
    return existing_tracks


def get_path_components(mp3_tags: pd.Series) -> list:
    # Returns the path valid components required to create the file path for
    # storing from a mp3 tags pandas series
    path_components = [rm_char(f) for f in (
        mp3_tags.album_artist,
        mp3_tags.album,
        mp3_tags.title
    )]

    # I would like to dedicate this line the XXXTENTACION,
    # who came up with an album called '?'.
    path_components = [c if any(c) else 'ILLEGAL_CHARACTERS_ONLY' for c in path_components]
    return path_components


def strip_url(url: str) -> str:
    # Removes the scheme and domain from a URL
    return url.split('://')[-1].split('www.')[-1]


def timeout_handler(func, *args, **kwargs):
    max_time_outs = 10
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


def unique_fname(file_path):
    fpath = str(file_path)

    if not os.path.isfile(fpath):
        return fpath

    directory = os.path.dirname(fpath)
    filename, extension = os.path.splitext(os.path.basename(fpath))
    new_filename = filename
    i = 2

    while os.path.exists(os.path.join(directory, new_filename + extension)):
        new_filename = f"{filename} ({i})"
        i += 1

    full_str = os.path.join(directory, new_filename + extension)

    # Convert back to input instance type:
    new_file_path = file_path.__class__(full_str)
    return new_file_path

