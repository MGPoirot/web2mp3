from initialize import spotify_api
from utils import _parse_retry_after_seconds
from tag_manager import get_track_tags, manual_track_tags
from spotipy.exceptions import SpotifyException
import requests
import logging
import time
import random
from typing import Tuple, List

# PSA: strictly define all substring patterns to avoid conflicts
# the name of the module
name = 'spotify'

# what the tool can receive from the module
target = 'tags'

# patterns to match in a URL
url_patterns = ['open.spotify.com', 'spotify.link', 'spotify.', ]

# substring to recognize a playlist object
playlist_identifier = '/playlist/'
album_identifier = '/album/'


class _SpotifyRateLimiter:
    """A minimal rate limiter to avoid sustained Spotify throttling.

    Spotify rate limiting is based on a rolling window. Once we see an HTTP 429,
    we switch into a paced mode where we ensure *subsequent* Spotify API calls
    are spaced out (default 0.4s => max ~150 calls/min).

    This doesn't guarantee avoiding 429s (other limits may apply), but it makes
    our request pattern stable and helps recovery.
    """

    def __init__(self, paced_interval_s: float = 0.4, decay_s: float = 300.0):
        self.paced_interval_s = float(paced_interval_s)
        self.decay_s = float(decay_s)
        self._paced_until_ts: float = 0.0
        self._next_call_ts: float = 0.0

    def note_throttled(self) -> None:
        now = time.monotonic()
        self._paced_until_ts = max(self._paced_until_ts, now + self.decay_s)

    def maybe_sleep_before_call(self) -> None:
        now = time.monotonic()
        if now >= self._paced_until_ts:
            return

        # paced mode: enforce spacing
        if now < self._next_call_ts:
            time.sleep(self._next_call_ts - now)
            now = time.monotonic()

        self._next_call_ts = now + self.paced_interval_s


_spotify_rl = _SpotifyRateLimiter()


def _spotify_notify(logger: logging.Logger | None, message: str) -> None:
    """Log once (no duplicate stderr printing)."""
    if logger:
        logger.warning("%s", message)
    else:
        # Fallback: avoid double prints; this should still be visible in CLI runs.
        print(message)


def spotify_call_with_backoff(
    func,
    *args,
    logger: logging.Logger | None = None,
    max_retries: int = 10,
    base_sleep_s: float = 2.0,
    max_sleep_s: float = 60.0,
    paced_interval_s: float = 0.4,
    **kwargs,
):
    """Spotify-specific backoff wrapper.

    Behavior:
    - Before every call, if we've been throttled recently, enforce pacing
      (default 0.4s between calls => ~150 calls/min).
    - On HTTP 429: use Retry-After when present; otherwise exponential backoff.
    - Retry up to max_retries, then raise RuntimeError.

    This wrapper is intentionally kept in the Spotify module (platform-specific).
    """

    # keep the limiter configured from call sites (if they override it)
    _spotify_rl.paced_interval_s = float(paced_interval_s)

    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        # If we were throttled recently, keep the entire app in a paced mode.
        _spotify_rl.maybe_sleep_before_call()

        try:
            return func(*args, **kwargs)

        except SpotifyException as e:
            if getattr(e, "http_status", None) != 429:
                raise

            last_exc = e
            _spotify_rl.note_throttled()

            headers = getattr(e, "headers", None) or getattr(e, "response_headers", None)
            retry_after = _parse_retry_after_seconds(headers)
            if retry_after is None:
                retry_after = min(base_sleep_s * (2 ** (attempt - 1)), max_sleep_s)
                retry_after += random.random()  # jitter

            _spotify_notify(
                logger,
                f"Spotify throttling (HTTP 429) on {getattr(func, '__name__', func)}; "
                f"Retry-After={float(retry_after):.1f}s ({attempt}/{max_retries})",
            )
            time.sleep(float(retry_after))
            continue

    raise RuntimeError(
        f"Rate-limit retries exhausted calling {getattr(func, '__name__', func)}"
    ) from last_exc


def spotify_timeout_handler(func, *args, **kwargs):
    """Backward-compatible-ish wrapper for spotipy calls.

    Accepts the same call sites as the old utils.timeout_handler:
      - max_time_outs
      - _logger
    """

    max_time_outs = int(kwargs.pop("max_time_outs", 10))
    logger = kwargs.pop("_logger", None) or kwargs.pop("__logger", None)
    return spotify_call_with_backoff(
        func,
        *args,
        logger=logger,
        max_retries=max_time_outs,
        paced_interval_s=0.4,
        **kwargs,
    )


def url_unshortner(object_url: str) -> str:
    if 'spotify.link' in object_url:
        # Don't allow this to block forever on a flaky network
        r = requests.head(object_url, allow_redirects=True, timeout=15)
        object_url = r.url
    return object_url


def general_handler(url: str, method) -> list:
    """
    Handles objects containing multiple tracks such as playlists and albums.
    Returns a list of track URLs
    :param url:     Object url
    :type url:      str
    :param method:  Method to call on the spotify_api
    :type method:   function
    :return:
    """
    uri = url2uri(url, raw=True)
    try:
        results = spotify_timeout_handler(method, uri)['tracks']
    except RuntimeError as e:
        # Exhausted retries (likely heavy throttling)
        print(str(e))
        return []
    except SpotifyException as e:
        mtd = method.__name__.capitalize()
        if e.http_status == 404:
            print(f'{mtd}NotFound: The object you are looking for is probably '
                  f'private')
        else:
            print(f'Unknown Spotify Error in retrieving {mtd} items')
        return []
    object_items = results['items']
    while results['next']:
        # spotify_api.next may also be throttled (HTTP 429)
        try:
            results = spotify_timeout_handler(spotify_api.next, results)
        except RuntimeError as e:
            print(str(e))
            return []
        object_items.extend(results['items'])
    if 'track' in object_items[0]:
        object_items = [i['track'] for i in object_items]
    # TODO: Somehow, sometimes t is None when multiple URLs are provided?
    # The current line fixes it, but what happens? Potentially returns empty list for unknown reason.
    # object_urls = [uri2url(t['id']) for t in object_items]
    object_urls = [uri2url(t['id']) for t in object_items if t is not None and t['id'] is not None]

    # omit objects that did not have a URL, such as unavailable content
    object_urls = [u for u in object_urls if u is not None]
    return object_urls


def playlist_handler(url: str) -> list:
    # Forwards the playlist method to the general_handle
    return general_handler(url, spotify_api.playlist)


def album_handler(url: str) -> list:
    # Forwards the album method to the general_handle
    return general_handler(url, spotify_api.album)


def sort_lookup(query: dict, matched_obj: dict | None) -> Tuple[str | None, dict | None]:
    # Sorts the mp3 URL and track tags
    track_uri = None if matched_obj is None else matched_obj['track_uri']
    track_tags = query
    return track_uri, track_tags


def get_search_platform():
    # Returns the module that handles the search platform
    from modules import youtube
    return youtube


def item2desc(item: dict) -> Tuple[str]:
    item = get_track_tags(item, do_light=True)
    return item['title'], item['artist']


def get_description(track_url: str, **kwargs) -> dict | None:
    market = kwargs['market']
    # Gets information about the track that will be used as query for matching
    try:
        item = spotify_timeout_handler(
            spotify_api.track,
            track_url,
            market=market,
            max_time_outs=kwargs.get("max_time_outs", 10),
            _logger=kwargs.get("logger"),
        )
    except RuntimeError:
        # Retries exhausted (most commonly due to heavy throttling)
        return None
    except SpotifyException:
        # The track was not found
        return None

    if not item:
        return None

    # Be defensive: don't assume Spotify response is always populated.
    item['title'] = item.pop('name', None)
    return get_track_tags(item, logger=kwargs.get("logger"))


def url2uri(url: str, raw=False) -> str:
    uri = url.split('?')[0].split('/track/')[-1].split('/playlist/')[-1]
    domain = '' if raw else 'spotify.'
    return f'{domain}{uri}'


def uri2url(uri: str) -> str | None:
    return f"https://open.spotify.com/track/{uri.split('.')[-1]}"


def search(search_query, **kwargs) -> List[dict]:
    search_limit = kwargs['search_limit']
    market = kwargs['market']
    try:
        results = spotify_timeout_handler(
            spotify_api.search,
            q=search_query,
            limit=search_limit,
            market=market,
            type='track',
            max_time_outs=kwargs.get("max_time_outs", 10),
            _logger=kwargs.get("logger"),
        )
    except RuntimeError:
        return []
    items = results['tracks']['items']

    # Rename track name to track title
    for item in items:
        item['title'] = item.pop('name')
    return items


def t_extractor(*items, query_duration=1) -> list:
    # Returns duration of a track from a list of tracks as float
    return [i['duration_ms'] / 1000 / query_duration for i in items]


def validate_items(items: List[dict]) -> List[int]:
    """
    Validates the presence and population of 'title' and 'videoId' fields
    in a list of dictionaries.

    AFAIK Spotify meta data is always complete

    :param items: A list of dictionaries to validate.
    :return: A list of indices (1-based) for dictionaries that have both
             'title' and 'videoId' populated.
    :rtype: List[int]
    """
    return list(range(1, len(items) + 1))

def get_meta_info(item: dict) -> dict:
    return get_track_tags(item)


def manual_handler(print_space=24, **kwargs) -> dict:
    logger: logging.Logger = kwargs.get('logger') or logging.getLogger(__name__)
    logger.info('Provide manual track info: ')
    return manual_track_tags(print_space=print_space, **kwargs)
