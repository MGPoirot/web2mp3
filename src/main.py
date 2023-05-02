import sys
sys.path.append('src')
from initialize import log_dir
from utils import Logger, input_is, get_url_platform, shorten_url, hms2s, \
    get_path_components, track_exists, sanitize_track_name, strip_url, flatten
from tag_manager import get_track_tags, manual_track_tags, get_tags_uri
import sys
import pandas as pd
import re
from song_db import set_song_db, get_song_db
from download_daemon import start_daemons
from unidecode import unidecode
import click
from click import Choice


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
    rip = lambda arg: re.sub(r'\W+', '', unidecode(arg.lower()))
    artist_name = artist_name.lower()
    artist_name = artist_name[4:] if artist_name[:4] == 'the ' else artist_name
    track_name = sanitize_track_name(track_name)
    return rip(track_name) in rip(title) \
        and rip(artist_name) in rip(title)


def lookup(query: pd.Series, platform, logger=print, **kwargs) -> \
        pd.Series:
    """
    Search for a track on a specified platform and return the best match.

    :param query: A pandas series containing the track information.
        This should contain at least the following columns:
        - 'duration'
        - 'title' and 'artist' or 'video_title'
    :type query: pandas.Series

    :param platform: The platform to search on. Currently supported options
        are 'spotify' and 'youtube'.
    :type platform: module

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
    ps = kwargs['print_space']
    default_response = kwargs['response']
    duration_tolerance = kwargs['tolerance']
    market = kwargs['market']
    matched_obj = None  # This is what we will return

    # Sanitize default response
    accept_origin = 'the user' if default_response is None else 'default'

    # Define what track information we have already received
    if platform.name == 'spotify':
        title = query.video_title
        search_query = title
    elif platform.name == 'youtube':
        name = query.title
        artist = query.artist
        if hasattr(query, 'video_title'):  # For manual retries
            search_query = query.video_title
        else:
            search_query = f'{name} - {artist}'
    else:
        raise ValueError(f'Unknown platform "{platform}"')

    # Query the desired platform
    qstr = search_query if len(search_query) < 53 else search_query[:50] + '...'
    logger(f'Searching {platform.name} for:'.ljust(ps), f'"{qstr}"')
    items = platform.search(search_query, **kwargs)

    # Check if one of our search results matches our query
    for n, item in enumerate(items, 1):
        # Extract information from our query results
        if platform.name == 'spotify':
            item_duration = item['duration_ms'] / 1000
            item_tags = get_track_tags(item, do_light=True)
            name = item_tags.title
            artist = item_tags.album_artist
            item_descriptor = f'{name} - {artist}'
        elif platform.name == 'youtube':
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
        logger(''.rjust(ps),
               f'{n}) {item_descriptor[:47].ljust(47)} {relative_duration:.0%}')
        # Check if the search result is a match
        if is_clear_match(name, artist, title) and is_duration_match:
            logger(f'Clear {platform.name} match:'.ljust(ps),
                   f'{item_descriptor}')
            if platform.name == 'spotify':
                matched_obj = get_track_tags(item, do_light=False)
            else:
                matched_obj = pd.Series({'track_url': item['link'],
                                         'video_title': item_descriptor,
                                         'duration': item_duration})
            break

    # Without clear match provide the user with options:
    if matched_obj is None:
        logger(f'No clear {platform.name} match. Select:')
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
                selected_item = items[idx]

                if platform.name == 'spotify':
                    matched_obj = get_track_tags(track_item=selected_item)
                    item_descriptor = f'{matched_obj.title} - ' \
                                      f'{matched_obj.album_artist}'
                elif platform.name == 'youtube':
                    item = selected_item
                    item_descriptor = item['title']
                    item_duration = hms2s(item['duration'])
                    matched_obj = pd.Series({'track_url': item['link'],
                                             'video_title': item_descriptor,
                                             'duration': item_duration})
                logger(f'Match accepted by {accept_origin}: '
                       f''.ljust(ps), item_descriptor)

        elif input_is('Retry', proceed):
            logger(f'Provide new info for {platform.name} query: ')
            search_query = input('>>> Track name and artist? '
                                 ''.ljust(ps))
            query.video_title = search_query

        elif input_is('Manual', proceed):
            if platform.name == 'spotify':
                logger('Provide manual track info: ')
                matched_obj = manual_track_tags(market=market)
            elif platform.name == 'youtube':
                matched_obj = input('>>> Provide YouTube URL: '
                                    ''.ljust(ps)).split('&')[0]

        elif input_is('Abort', proceed):
            matched_obj = False

        elif input_is('Change market', proceed):
            market = input('>>> Market code?'.ljust(ps)) or None
            logger('Market changed to:'.ljust(ps))
            kwargs['market'] = market
        else:
            logger(f'Invalid input "{proceed}"')

    # Give it another try with our updated arguments
    if matched_obj is None:
        matched_obj = lookup(
            query=query,
            platform=platform,
            logger=logger,
            **kwargs,
        )
    return matched_obj


def match_audio_with_tags(track_url: str, **kwargs):
    """
    This function matches a given URL, and writes what it found to the song
    database, after which it calls this function again, but as a background
    process, and finishes.
    """
    # Get the arguments
    ps = kwargs['print_space']
    market = kwargs['market']
    do_overwrite = kwargs['do_overwrite']

    # Create a logger object for this URL
    logger_path = log_dir.format(shorten_url(track_url))
    logger = Logger(logger_path, verbose=True)

    # Get the source platform module and the platform we need to match it with
    source = get_url_platform(track_url)
    if source is None:  # matching failed
        return
    else:
        logger(f'New {source.name} URL:'.ljust(ps), strip_url(track_url))
    search = source.get_search_platform()

    # Skip in case the URL is already in the database
    if source.url2uri(track_url) in get_song_db().index and not do_overwrite:
        print(f'Skipped: {source.name} URI exists in Song Data Base.\n')
        return

    # Get a description of the object to use for matching
    query = source.get_description(track_url, logger, market)
    if query is None:  # Failed to retrieve query
        logger(f'Failed: No {source.name} query for matching.\n')
        return

    # If the query contains this field it cannot be empty or zero.
    req_fields = ['duration', 'title', 'album', 'artist']
    if any([not bool(query[c]) for c in req_fields if c in query]):
        logger(f'Skipped: URL refers to empty object.')
        set_song_db(source.url2uri(track_url))
        return

    # Match the object
    match_obj = lookup(query=query,
                       platform=search,
                       logger=logger,
                       **kwargs)

    if match_obj is False:
        logger(f'Failed: No match between {source.name} and'
               f' {source.get_search_platform().name} items\n')
        return

    track_uri, track_tags = source.sort_lookup(query, match_obj)
    tags_uri = get_tags_uri(track_tags)
    source_uri = source.url2uri(track_url)  # 1 id may >1  urls

    #  Check if the found tracks is already in the database
    song_db_indices = get_song_db().index
    artist_p, _, track_p = get_path_components(track_tags)

    skip = True
    if not do_overwrite:
        skip = False
    elif track_exists(artist_p, track_p, logger=logger):
        logger('Skipped: FileExists')
    elif tags_uri in song_db_indices:
        logger('Skipped: TagsExists')
    elif track_uri in song_db_indices:
        logger('Skipped: TrackExists')
    elif source_uri in song_db_indices:
        logger('Skipped: SourceExists')
    else:
        skip = False

    # Set song database entries
    set_song_db(tags_uri)
    set_song_db(source_uri)
    set_song_db(track_uri)
    if not skip:
        keys = 'print_space', 'max_daemons', 'verbose', 'verbose_continuous', \
            'do_overwrite', 'quality'

        # TODO: REMOVE THIS AS SOON AS OLD SONG DB HAS BEEN UPDATED
        foo = get_song_db()
        if not any(i for i in foo.columns if 'kwarg' in i):
            import numpy as np
            from initialize import song_db_file
            kkeys = ['kwarg_' + k for k in keys]
            for k in kkeys:
                if '_space' in k or 'max_d' in k or '_quali' in k:
                    dtype = {'dtype': pd.Int64Dtype()}
                elif 'verbose' in k or 'do_overwrite' in k:
                    dtype = {'dtype': pd.BooleanDtype()}
                foo.insert(loc=len(foo.columns), column=k,
                           value=pd.array(data=[np.nan] * len(foo), **dtype))
            foo.to_pickle(song_db_file.format(''))
            # TODO: SEE ABOVE

        kwg_df = pd.Series({f'kwarg_{k}': kwargs[k] for k in keys})
        track_tags = pd.concat([track_tags, kwg_df])
        set_song_db(track_uri, track_tags)
        logger('Success: Download added\n')
    return


def unpack_url(url: str) -> list:
    # Skip empty URL
    if not url:
        return []

    # Anything after '&' is not of interest
    url = url.split('&')[0]

    # Identify the platform where the URL is from
    platform = get_url_platform(url)
    if platform is None:
        print('Failed to unpack URL')
        return []

    # Check if the URL is a reference to a batch of tracks
    if platform.playlist_identifier in url:
        urls = platform.playlist_handler(url)
    elif platform.album_identifier in url:
        urls = platform.album_handler(url)
    else:
        urls = [url]
    return urls


def main(**kwargs):
    # Get arguments
    ps = kwargs['print_space']
    urls = kwargs['urls']
    init_daemons = kwargs['init_daemons']
    headless = kwargs['headless']
    max_daemons = kwargs['max_daemons']
    verbose = kwargs['verbose']

    # Unpack URLs that contain playlists or albums
    urls = flatten([unpack_url(u) for u in urls])

    # Process URLs that were already provided
    for url in urls:
        match_audio_with_tags(url, **kwargs)
        # Start the daemons during the matching of further items
        if input_is('During', init_daemons):
            n_started = start_daemons(max_daemons, verbose)
            if n_started and not verbose:
                print(f'{n_started} DAEMONs started')
    # Start the daemons after the matching of all items
    if input_is('After', init_daemons):
        n_started = start_daemons(max_daemons, verbose)
        if n_started and not verbose:
            print(f'{n_started} DAEMONs started')

    # Ask for more URLs with previously provided arguments
    if not headless:
        while True:
            input_url = input('>>> URL or [Abort]?'.ljust(ps))
            if not input_url or input_is('Abort', input_url):
                print('Bye Bye!')
                sys.exit()
            else:
                input_urls = input_url.split(' ')
                kwargs['urls'] = input_urls
                main(**kwargs)


@click.command("cli", context_settings={'show_default': True})
@click.version_option()
@click.argument("urls", nargs=-1)
@click.option("-r", "--response", default=None,
              type=Choice(['1', 'Abort'], case_sensitive=False),
              help="Response when no match.")
@click.option("-x", "--max_daemons", default=4,
              help="Maximum number of DAEMONs.")
@click.option("-h", "--headless", is_flag=True, default=False,
              help="To exit when arguments have been processed.")
@click.option("-i", "--init_daemons", default="during",
              type=Choice(['During', 'After', 'Not'], case_sensitive=False),
              help="When to initiate DAEMONs.")
@click.option("-v", "--verbose", is_flag=True, default=False,
              help="To download in foreground.")
@click.option("-c", "--verbose_continuous", is_flag=True, default=False,
              help="When verbose, to continue after 1 item.")
@click.option("-t", "--tolerance", default=0.10,
              help="Duration difference threshold.")
@click.option("-m", "--market", default="NL",
              help="Spotify API market.")
@click.option("-l", "--search_limit", default=5,
              help="Tracks to check for match.")
@click.option("-d", "--avoid_duplicates", is_flag=True, default=True,
              help="To skip if file exists.")
@click.option("-o", "--do_overwrite", is_flag=True, default=False,
              help="To proceed if URL in DB.")
@click.option("-p", "--print_space", default=24,
              help="Whitespaces used when logging.")
@click.option("-w", "--max_time_outs", default=10,
              help="Attempts when TimeOut.")
@click.option("-q", "--quality", default=320,
              help="Audio quality in kB/s")
def click_processor(**kwargs):
    main(**kwargs)


if __name__ == '__main__':
    click_processor()

# os.system(f'sudo su plex -s /bin/bash')
# We will want to use the API for scanning:
# http://192.168.2.1:32400/library/sections/6/refresh?path=/srv/dev-disk-by-uuid-1806e0be-96d7-481c-afaa-90a97aca9f92/Plex/Music/Lazzo&X-Plex-Token=QV1zb_72YxRgL3Vv4_Ry
# print('you might want to run...')
# print(f"'/usr/lib/plexmediaserver/Plex\ Media\ Scanner --analyze -d '{root}'")