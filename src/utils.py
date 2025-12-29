from initialize import music_dir, Path
import pickle
import os
import inspect
from datetime import datetime
import json
import sys
import re
from glob import iglob
from time import sleep
import random
from importlib import import_module
from json.decoder import JSONDecodeError
from collections.abc import Iterable
import modules
import importlib
from requests.exceptions import ReadTimeout
import requests
import logging
from functools import lru_cache
from types import ModuleType
import pkgutil


@lru_cache(maxsize=1)
def _build_platform_pattern_index() -> dict[str, str]:
    """
    Build a mapping from URL substring pattern -> module name (domain).
    Runs once per process.
    """
    patterns: dict[str, str] = {}

    # modules is your package; pkgutil iterates without opening lots of handles repeatedly
    for m in pkgutil.iter_modules(modules.__path__):
        if m.ispkg:
            continue

        mod = import_module(f"{modules.__name__}.{m.name}")

        # Expect each module to define: name (e.g. 'spotify') and url_patterns (iterable of substrings)
        url_patterns = getattr(mod, "url_patterns", None)
        domain = getattr(mod, "name", None)

        if not domain or not url_patterns:
            continue

        for p in url_patterns:
            # last write wins; you could warn on duplicates if you want
            patterns[str(p)] = str(domain)

    return patterns


def clip_path_length(path: str | Path, max_path_length: int = 255) -> str | Path:
    """
    Prevents OSError: [Errno 36] File name too long, but clipping path
    name components to max_path_length Unicode characters.
    """
    output_type = str
    if isinstance(path, Path):
        path = str(path)
        output_type = Path
    return output_type(os.sep.join([i.encode('utf-8')[:max_path_length].decode('utf-8') for i in path.split(os.sep)]))



def get_url_platform(track_url: str, logger: logging.Logger | None = None):
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
    patterns = _build_platform_pattern_index()

    for pattern, domain in patterns.items():
        if pattern in track_url:
            try:
                return import_module(f"modules.{domain}")
            except ModuleNotFoundError:
                return None

    logger = logger or logging.getLogger(__name__)
    logger.warning(
        'No pattern found in "%s". Known patterns: %s',
        track_url,
        '; '.join(patterns.keys()),
    )
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
        > shorten_url('spotify:track:7h5crXBSY5sspXRIlklv74')
        7h5crXBSY5sspXRIlklv74
    """
    if '=' in url:
        url = url.split('=')[1] if '=' in url else url
    else:
        url = url.split('/')[-1]
    return url.split('&')[0].split(':')[0]



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
                start = content.find('{')
                stop = -1
                waiting = 0
                for i, c in enumerate(content):
                    if c == '{':
                        waiting += 1
                    elif c == '}':
                        if waiting:
                            waiting -= 1
                        else:
                            stop = i
                stop = content.find('}') + 1
                if start < 0 or stop < 0:
                    junk = content
                    recovered = {}
                else:
                    part = content[start:stop]
                    try:
                        recovered = json.loads(part)
                        junk = content[stop:]
                    except JSONDecodeError:
                        junk = content
                        recovered = {}
                        pass
                # Save new files
                new_junk_file = unique_fname(source_path)
                json_out(junk, new_junk_file)
                print(f'Corrupted data stored to: "{new_junk_file}"')
                json_out(recovered, source_path)
                if recovered != {}:
                    print(f'Data recovered and saved to: "{source_path}"')
                else:
                    print('No data was recovered, but operation can continue')
                return recovered
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
            print(f'Writing in binary mode because of error "{e}".')
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

    # Remove use of &
    track_name = track_name.replace('&', 'and')

    # Perform the removal
    for w1 in words_to_remove:
        for w2 in second_words:
            pattern = f'{w1}{w2}\s*{year_pattern.pattern}|\s*{w1}{w2}'
            track_name = re.sub(pattern, '', track_name)
    track_name = re.sub(year_pattern, '', track_name)

    # Remove any leading or trailing spaces
    track_name = track_name.strip()
    return track_name


def track_exists(artist_p: str, track_p: str, logger: logging.Logger | None = None) -> list:
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
    pattern = re.compile(
        re.escape(track_p).replace(r"\ ", r"[\s_]*"),
        re.IGNORECASE | re.UNICODE,
    )

    glob_pat = os.path.join(music_dir, artist_p, "*", "*.mp3")
    matches: list[str] = []

    # Stream results; no intermediate "filenames = [...]"
    for fpath in iglob(glob_pat):
        fn = os.path.basename(fpath)
        if pattern.search(fn):
            matches.append(fn)

    if matches:
        logger = logger or logging.getLogger(__name__)
        logger.warning("FileExistsWarning: %s - %s", track_p, artist_p)
        for i, fn in enumerate(matches, 1):
            logger.warning("   %s)   %s\n ", i, fn.split(os.extsep)[0])

    return matches


def get_path_components(mp3_tags: dict) -> list:
    # Returns the path valid components required to create the file path for
    # storing from a mp3 tags dict
    path_components = [rm_char(f) for f in (
        mp3_tags['album_artist'],
        mp3_tags['album'],
        mp3_tags['title']
    )]

    # I would like to dedicate this line the XXXTENTACION,
    # who came up with an album called '?'.
    path_components = [c if any(c) else 'ILLEGAL_CHARACTERS_ONLY' for c in
                       path_components]
    return path_components


def strip_url(url: str) -> str:
    # Removes the scheme and domain from a URL
    return url.split('://')[-1].split('www.')[-1]


def _parse_retry_after_seconds(headers) -> int | None:
    """Return Retry-After in seconds if present/parseable."""
    if not headers:
        return None
    try:
        # handle case-insensitivity and different header container types
        for k in ("Retry-After", "retry-after", "RETRY-AFTER"):
            if k in headers:
                v = headers.get(k)
                try:
                    return int(float(v))
                except (TypeError, ValueError):
                    return None
    except Exception:
        return None
    return None


def call_with_backoff(
    func,
    *args,
    logger: logging.Logger | None = None,
    max_retries: int = 10,
    base_sleep_s: float = 2.0,
    max_sleep_s: float = 60.0,
    **kwargs,
):
    """Call *func* with throttling-aware retries.

    - For Spotify 429 responses (Spotipy's SpotifyException with http_status==429),
      prefer the Retry-After header when available.
    - Falls back to exponential backoff with a small jitter.
    - Also retries on network timeouts.

    Returns the function result.

    IMPORTANT: If retries are exhausted, this raises RuntimeError.
    """

    # local import so utils.py stays importable even when spotipy isn't installed
    try:
        from spotipy.exceptions import SpotifyException  # type: ignore
    except Exception:  # pragma: no cover
        SpotifyException = ()  # type: ignore

    logger = logger or logging.getLogger(__name__)

    def _notify(message: str) -> None:
        """Surface throttling/timeout waits to the user.

        Many runs *do* have a StreamHandler attached to the logger (console),
        in which case printing as well would duplicate messages. We therefore:
        - always log (best effort)
        - only print to stderr if the logger has no StreamHandler
        """

        try:
            logger.warning("%s", message)
        except Exception:
            pass

        has_stream_handler = False
        try:
            for h in getattr(logger, "handlers", []) or []:
                if isinstance(h, logging.StreamHandler):
                    has_stream_handler = True
                    break
        except Exception:
            has_stream_handler = False

        if not has_stream_handler:
            try:
                sys.stderr.write(message + "\n")
                sys.stderr.flush()
            except Exception:
                pass
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)

        except (TimeoutError, ReadTimeout) as e:
            last_exc = e
            wait_s = min(base_sleep_s * attempt, max_sleep_s)
            _notify(
                f"Timeout while calling {getattr(func, '__name__', func)}; "
                f"sleeping {wait_s:.1f}s ({attempt}/{max_retries})"
            )
            sleep(wait_s)
            continue

        except SpotifyException as e:  # type: ignore
            http_status = getattr(e, "http_status", None)
            if http_status != 429:
                raise

            last_exc = e
            headers = getattr(e, "headers", None) or getattr(e, "response_headers", None)
            retry_after = _parse_retry_after_seconds(headers)
            if retry_after is None:
                retry_after = min(base_sleep_s * (2 ** (attempt - 1)), max_sleep_s)
                retry_after += random.random()  # jitter

            _notify(
                f"Spotify throttling (HTTP 429) on {getattr(func, '__name__', func)}; "
                f"Retry-After={float(retry_after):.1f}s ({attempt}/{max_retries})"
            )
            sleep(float(retry_after))
            continue

        except requests.exceptions.HTTPError as e:
            # Some call paths may raise HTTPError directly.
            resp = getattr(e, "response", None)
            status = getattr(resp, "status_code", None)
            if status != 429:
                raise

            last_exc = e
            retry_after = _parse_retry_after_seconds(getattr(resp, "headers", None))
            if retry_after is None:
                retry_after = min(base_sleep_s * (2 ** (attempt - 1)), max_sleep_s)
                retry_after += random.random()

            _notify(
                f"HTTP 429 throttling on {getattr(func, '__name__', func)}; "
                f"Retry-After={float(retry_after):.1f}s ({attempt}/{max_retries})"
            )
            sleep(float(retry_after))
            continue

    raise RuntimeError(
        f"Rate-limit retries exhausted calling {getattr(func, '__name__', func)}"
    ) from last_exc


def timeout_handler(func, *args, **kwargs):
    # Backward-compatible wrapper kept because many modules import it.
    # You can also pass max_time_outs=N to override.
    max_time_outs = int(kwargs.pop("max_time_outs", 10))
    logger = kwargs.pop("_logger", None) or kwargs.pop("__logger", None)
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
    return call_with_backoff(
        func,
        *args,
        logger=logger,
        max_retries=max_time_outs,
        **kwargs,
    )


def unique_fname(file_path: str | Path) -> str | Path:
    """
     Preserves file_path class type in last line
    """

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