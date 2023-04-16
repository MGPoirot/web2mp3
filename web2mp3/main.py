import sys
import pandas as pd
import pytube
from time import sleep
from utils import spotify, Logger, input_is, get_url_domain, shorten_url, hms2s, \
    log_dir, get_path_components, track_exists
from settings import print_space, default_market, default_tolerance, \
    search_limit
from tag_manager import get_track_tags, manual_track_tags
import youtube
import soundcloud
from song_db import set_song_db, get_song_db
from download_daemon import start_daemon
from youtubesearchpython import VideosSearch
from unidecode import unidecode
import re

def is_clear_match(track_name: str, artist_name: str, title: str) -> bool:
    """
    Checks if the given track name and artist name are a clear match for a
    given title (case-, diacritic- and non-alphanumeric insensitive).

    :param track_name: The name of the track to be checked.
    :type track_name: str
    :param artist_name: The name of the artist to be checked.
    :type artist_name: str
    :param title: The title to check against.
    :type title:

    :return: True if both the track name and artist name can be found in the
    title, otherwise False.
    :rtype: bool

    Example:
    > is_clear_match("Lose You To Love Me", "Selena Gomez",
     "selena gomez - Lose You To Love Me (Official Music Video)")
    True
    """
    # TODO: add more lenient matching: accents and special characters
    rip = lambda arg: re.sub(r'\W+', '', unidecode(arg).lower())
    return rip(track_name) in rip(title) and rip(artist_name) in rip(title)


def lookup(query: pd.Series, platform: str, logger=print,
           duration_tolerance=0.05, market='NL', default_response=None,
           search_limit=5):
    """
    Search for a track on a specified platform and return the best match.

    :param query: A pandas series containing the track information.
        This should contain at least the following columns:
        - 'duration'
        - 'title' and 'artist' or 'video_title'
    :type query: pandas.Series

    :param platform: The platform to search on. Currently supported options
        are 'spotify' and 'youtube'.
    :type platform: str

    :param logger: A logging object for printing information and errors.

    :param duration_tolerance: The percentage difference between the
        duration of the search result and the query duration that is still
        considered a match. Default is 0.05.
    :type duration_tolerance: float

    :param market: A two-letter Spotify market code for the market to search in.
        Default is 'NL'.
    :type market: str

    :param default_response: If provided, this will be used to select a search
        result without requiring user input.
        - If this is a string representing an integer, that option will be
          selected.
        - If this is a string that is not an integer, the function will look for
          a matching input in the user prompt.
        Default is None.
    :type default_response: str or None

    :param search_limit: The maximum number of search results to retrieve from
        the platform. Default is 5.
    :type search_limit: int

    :returns: If a clear match is found, the function returns either a
        YouTube URL if the plaform is 'youtube' or a pandas.Series with track
        tags. If the search is cancelled by the user the function returns False.
    :rtype: pandas.Series or str or bool
    """
    matched_obj = None  # This is what we will return

    # Sanitize default response
    accept_origin = 'the user' if default_response is None else 'default'
    if isinstance(default_response, str):
        if default_response.isdigit():
            # If we always want option X, we do not have to look any further
            search_limit = int(default_response)

    # Define what track information we have already received
    if platform == 'spotify':
        title = query.video_title
        search_query = title
    elif platform == 'youtube':
        name = query.title
        artist = query.artist
        if hasattr(query, 'video_title'):  # For manual retries
            search_query = query.video_title
        else:
            search_query = f'{name} - {artist}'
    else:
        raise ValueError(f'Uknown platform "{platform}"')

    # Query the desired platform
    logger(f'Searching {platform} for:'.ljust(print_space), f'"{search_query}"')
    items = []
    try:
        if platform == 'spotify':
            results = spotify.search(
                q=search_query,
                limit=search_limit,
                market=market,
                type='track'
            )
            items = results['tracks']['items']
        elif platform == 'youtube':
            results = VideosSearch(
                query=search_query,
                limit=search_limit
            ).result()
            items = results['result']
    except KeyboardInterrupt:
        matched_obj = False
    except TimeoutError:
        logger('spotify encountered a Timeout error. Try again in 2 seconds.')
        sleep(2)

    # Check if one of our search results matches our query
    for n, item in enumerate(items, 1):
        # Extract information from our query results
        if platform == 'spotify':
            item_duration = item['duration_ms'] / 1000
            item_tags = get_track_tags(item, logger, do_light=True)
            name = item_tags.title
            artist = item_tags.album_artist
            item_descriptor = f'{name} - {artist}'
        elif platform == 'youtube':
            item_duration = hms2s(item['duration'])
            item_descriptor = item['title']
            title = item['title']
        else:
            logger(f'Unknown platform "{platform}"')
            break

        # Check how the duration matches up with what we are looking for
        relative_duration = item_duration / query.duration
        is_duration_match = abs(relative_duration - 1) < duration_tolerance

        # Print a synopsis of our search result
        logger(''.rjust(print_space),
               f'{n}) {item_descriptor[:47].ljust(47)} {relative_duration:.0%}')
        # Check if the search result is a match
        if is_clear_match(name, artist, title) and is_duration_match:
            logger(f'Clear {platform} match'.ljust(print_space),
                   f'{item_descriptor}')
            if platform == 'spotify':
                matched_obj = get_track_tags(item, logger, do_light=False)
            else:
                matched_obj = item['link']
            break

    # Without clear match provide the user with options:
    if matched_obj is None:
        logger(f'No clear {platform} match. Select:')
        if default_response is None:
            item_options = '/'.join(
                [str(i + 1) if i else f'[{i + 1}]' for i in range(len(items))]
            )  # returns [1]/2/3/4/5 depending on the number of found items
            default = '1' if any(items) else 'Retry'
            proceed = input(
                f'>>> {item_options}/Retry/Manual/Abort/Change market: '
            ) or default
        else:
            proceed = default_response

        # Take action according to user input
        if proceed.isdigit():
            idx = int(proceed) - 1
            if idx > len(items):
                logger(f'Invalid index {idx} for {len(items)} options.')
            else:
                if platform == 'spotify':
                    matched_obj = get_track_tags(
                        track_item=items[idx],
                        logger=logger,
                        do_light=False
                    )
                    item_descriptor = f'{matched_obj.title} - ' \
                                      f'{matched_obj.album_artist}'
                elif platform == 'youtube':
                    item = items[idx]
                    item_descriptor = item['title']
                    matched_obj = item['link']
                logger(f'Match accepted by {accept_origin}: '
                       f''.ljust(print_space), item_descriptor)

        elif input_is('Retry', proceed):
            logger(f'Provide new info for {platform} query: ')
            search_query = input('>>> Track name and artist? '
                                 ''.ljust(print_space))
            query.video_title = search_query

        elif input_is('Manual', proceed):
            if platform == 'spotify':
                logger('Provide manual track info: ')
                matched_obj = manual_track_tags(market=market)
            elif platform == 'youtube':
                matched_obj = input('>>> Provide YouTube URL: '
                                    ''.ljust(print_space)).split('&')[0]

        elif input_is('Abort', proceed):
            matched_obj = False

        elif input_is('Change market', proceed):
            market = input('>>> Market code?'.ljust(print_space)) or None
            logger('Market changed to:'.ljust(print_space))

        else:
            logger(f'Invalid input "{proceed}"')

    # Give it another try with our updated arguments
    if matched_obj is None:
        matched_obj = lookup(
            query=query,
            platform=platform,
            logger=logger,
            duration_tolerance=duration_tolerance,
            market=market,
            default_response=default_response,
            search_limit=search_limit
        )
    return matched_obj


def match_audio_with_tags(track_url: str, logger: Logger,
                          duration_tolerance=0.05, market='NL',
                          default_response=None, search_limit=5):
    """
    This function matches a given URL, and writes what it found to the song
    database, after which it calls this function again, but as a background
    process, and finishes.
    """
    logger_verbose_default = logger.verbose
    logger.verbose = True

    # Get the information we need to perform the matching
    url_domain = get_url_domain(track_url)
    if url_domain is None:
        query = None
    elif url_domain == 'spotify':
        search_platform = 'youtube'
        item = spotify.track(track_url, market=market)
        track_tags = get_track_tags(item, logger=logger, do_light=False)
        query = track_tags
        track_url = None
    else:
        search_platform = 'spotify'
        if url_domain == 'youtube':
            module = youtube
        elif url_domain == 'soundcloud':
            module = soundcloud
        query = module.get_description(track_url, logger)
        track_tags = None

    # Perform matching and check results
    if query is None:
        logger(f'Failed: No {url_domain} query for matching.')
    else:
        matched_obj = lookup(query=query,
                             platform=search_platform,
                             logger=logger,
                             duration_tolerance=duration_tolerance,
                             market=market,
                             default_response=default_response,
                             search_limit=search_limit)
        if matched_obj is False:
            logger(f'Failed: No match between {url_domain} and'
                   f' {search_platform} items.\n')
        else:
            if url_domain == 'spotify':
                track_url = matched_obj
            elif url_domain == 'youtube':
                track_tags = matched_obj

            artist_p, _, track_p = get_path_components(track_tags)
            if not track_exists(artist_p, track_p, logger=logger):
                set_song_db(track_url, track_tags)
                logger('Success: Song DB entry created.\n')
            else:
                set_song_db(track_url, None)
                logger('Skipped: FileExists - Song DB entry set to None.\n')
    # Reset and return
    logger.verbose = logger_verbose_default
    return


def init_matching(*urls, default_response=None):
    for i, url in enumerate(urls):
        # Sanitize URL
        url = url.split('&')[0]
        if not url:
            continue

        # Identify the domain
        domain = get_url_domain(url)
        if domain is None:
            continue
        elif 'playlist' in url:  # Handling of playlists
            # Get playlist items
            if domain == 'youtube':
                playlist_urls = pytube.Playlist(url)
            elif domain == 'spotify':
                pl_uri = url.split('?')[0].split('/')[-1]
                playlist_items = spotify.playlist(pl_uri)['tracks']['items']
                playlist_urls = [
                    f"https://open.spotify.com/track/{t['track']['id']}" for t
                    in playlist_items]

            # Ask if to continue
            do_playlist = input(
                f'>>> Received playlist with {len(playlist_urls)} items. '
                f'Proceed? [Yes]/No  '.ljust(print_space))
            if input_is('No', do_playlist):
                print('Playlist skipped.')
                continue
            elif input_is('Yes', do_playlist) or not do_playlist:
                default_response = input(
                    '>>> Set default response procedure?: [None]/1/Abort  '
                    ''.ljust(print_space)) or None
                if default_response is None:
                    pass
                elif input_is('None', default_response):
                    default_response = None
                elif not input_is('1', default_response) and not input_is(
                        'Abort', default_response):
                    print('Invalid input:'.ljust(print_space),
                          f'"{default_response}"')
                    default_response = None
                init_matching(*playlist_urls, default_response=default_response)
            else:
                print('Invalid input:'.ljust(print_space), f'"{do_playlist}"')
        else:  # Handling of individual tracks
            if url in get_song_db():
                print('Skipped: Track exists in Song Data Base.\n')
                continue
            logger_path = log_dir.format(shorten_url(url))
            log_obj = Logger(logger_path)
            log_obj(
                f'{i}/{len(urls)} Received new {domain} URL'.ljust(print_space),
                url)
            match_audio_with_tags(
                track_url=url,
                logger=log_obj,
                duration_tolerance=default_tolerance,
                market=default_market,
                default_response=default_response,
                search_limit=search_limit
            )
        start_daemon()


if __name__ == '__main__':
    if len(sys.argv) == 1:  # No URL provided, run in Python mode
        while True:
            input_url = input('>>> URL or [Abort]?'.ljust(print_space))
            if not input_url or input_is('Abort', input_url):
                print('Bye Bye!')
                sys.exit()
            else:
                init_matching(*input_url.split(' '))
    else:
        input_urls = sys.argv[1:]
        init_matching(*input_urls)

# os.system(f'sudo su plex -s /bin/bash')
# We will want to use the API for scanning:
# http://192.168.2.1:32400/library/sections/6/refresh?path=/srv/dev-disk-by-uuid-1806e0be-96d7-481c-afaa-90a97aca9f92/Plex/Music/Lazzo&X-Plex-Token=QV1zb_72YxRgL3Vv4_Ry
# print('you might want to run...')
# print(f"'/usr/lib/plexmediaserver/Plex\ Media\ Scanner --analyze -d '{root}'")
