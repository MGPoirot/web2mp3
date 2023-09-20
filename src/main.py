import sys
sys.path.append('src')
from initialize import log_dir, default_market
from utils import Logger, input_is, get_url_platform, shorten_url, hms2s, \
    get_path_components, track_exists, sanitize_track_name, strip_url, flatten
from tag_manager import get_track_tags, manual_track_tags, get_tags_uri
import sys
import pandas as pd
import re
from song_db import set_song_db, get_song_db, song_db_template
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


def lookup(query: pd.Series, platform, logger=print, sort_by='duration',
           **kwargs) -> pd.Series:
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
        Default is set upon initialization.
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
            # # Uses the Spotify API for formatting,
            # # I have not found this to be beneficial
            # search_query = f'track:{name} artist:{artist}'
            search_query = f'{name} {artist}'
    else:
        raise ValueError(f'Unknown platform "{platform}"')

    # Query the desired platform
    qstr = search_query if len(search_query) < 53 else search_query[:50] + '...'
    logger(f'Searching {platform.name.capitalize()} for:'.ljust(ps), f'"{qstr}"')
    items = platform.search(search_query, **kwargs)



    # Sort the item list by relative durations
    rel_ts = platform.t_extractor(*items, query_duration=query.duration)
    if sort_by == 'duration' and None not in rel_ts:
        sort_obj = sorted(zip([abs(d - 1) for d in rel_ts], rel_ts, range(len(
            rel_ts))))
        items_and_durations = [(items[idx], rel_t) for _, rel_t, idx in sort_obj]
        # Sort the items, in case we need to get them by index
        items, rel_ts = zip(*items_and_durations)

    # Check if one of our search results matches our query
    if not any(items):
        logger(f'No results found for {accept_origin} search.')
        default_response = None
    for n, (item, rel_t) in enumerate(zip(items, rel_ts), 1):
        # Extract information from our query results
        if platform.name == 'spotify':
            item_tags = get_track_tags(item, do_light=True)
            name = item_tags.title
            artist = item_tags.album_artist
            item_desc = f'{name} - {artist}'
        elif platform.name == 'youtube':
            item_desc = item['title']
            title = item['title']
        else:
            logger(f'Unknown platform "{platform}"')
            break

        # Print a synopsis of our search result
        rel_t_str = f'{str(rel_t)}%' if rel_t is None else f'{rel_t:.0%}'
        logger(''.rjust(ps), f'{n}) {item_desc[:47].ljust(47)} {rel_t_str}')

        # Check how the duration matches up with what we are looking for
        is_duration_match = None if rel_t is None else \
                abs(rel_t - 1) < duration_tolerance

        # Check if the search result is a match
        if is_clear_match(name, artist, title) and is_duration_match:
            logger(f'Clear {platform.name} match:'.ljust(ps),
                   f'{item_desc}')
            if platform.name == 'spotify':
                matched_obj = get_track_tags(item, do_light=False)
            else:
                item_duration = platform.t_extractor(item)[0]
                matched_obj = pd.Series({'track_url': item['link'],
                                         'video_title': item_desc,
                                         'duration': item_duration})
            break


    # Without clear match provide the user with options:
    if matched_obj is None:
        no_match_status = f'No clear {platform.name} match. ' + '{}:'
        # Set appropriate response
        if default_response is not None:
            proceed = default_response
            logger(no_match_status.format(f'Default to {proceed}'))
        else:
            logger(no_match_status.format('Select'))
            if default_response is None:
                if any(items):
                    item_options = '/'.join([str(i + 1)
                                             for i in range(len(items))]) + '/'
                    default = '1'
                else:
                    default = 'Retry'
                prompt = f'>>> {item_options}Retry/Manual/Abort/Change market:'
                prompt.replace(default, f'[{default}]')
                proceed = input(prompt) or default

        # Take action according to proceed method
        if proceed.isdigit():
            idx = int(proceed) - 1
            if idx > len(items) or idx < 0:
                logger(f'Invalid index {idx + 1} for {len(items)} options.')
            else:
                selected_item = items[idx]

                if platform.name == 'spotify':
                    matched_obj = get_track_tags(track_item=selected_item)
                    item_desc = f'{matched_obj.title} - ' \
                                f'{matched_obj.album_artist}'
                elif platform.name == 'youtube':
                    item = selected_item
                    item_desc = item['title']
                    item_duration = hms2s(item['duration'])
                    matched_obj = pd.Series({'track_url': item['link'],
                                             'video_title': item_desc,
                                             'duration': item_duration})
                logger(f'Match accepted by {accept_origin}: '
                       f''.ljust(ps), item_desc)

        elif input_is('Retry', proceed):
            logger(f'Provide new info for {platform.name} query: ')
            search_query = input('>>> Track name and artist? '
                                 ''.ljust(ps))
            query.video_title = search_query

        elif input_is('Manual', proceed):
            if platform.name == 'spotify':
                logger('Provide manual track info: ')
                matched_obj = manual_track_tags(market=market,
                                                duration=query.duration)
                matched_obj['internet_radio_url'] = query['track_url']
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
    if matched_obj is None and default_response is None:
        matched_obj = lookup(
            query=query,
            platform=platform,
            logger=logger,
            **kwargs,
        )
    return matched_obj


def file_from_tags_exists(track_tags, logger=print, avoid_duplicates=True):
    if avoid_duplicates and track_tags is not None:
        artist_p, _, track_p = get_path_components(track_tags)
        if any(track_exists(artist_p, track_p, logger=logger)):
            return True
    return False


def do_match(track_url, source, logger=print, **kwargs):
    """
        The do_match function handles the heavy lifting of the matching process,
        it is wrapped by match_audio_with_tags to enable harmonized handling of
        errors and setting of the song_db.
    """
    # Get the arguments
    market = kwargs['market']
    do_overwrite = kwargs['do_overwrite']
    avoid_duplicates = kwargs['avoid_duplicates']
    ps = kwargs['print_space']
    track_uri = source.url2uri(track_url)

    # Skip in case the URL is already in the database
    if track_uri in get_song_db().index and not do_overwrite:
        return f'Skipped: TrackExists "{track_uri}"'

    # Get a description of the object to use for matching
    query = source.get_description(track_url=track_url,
                                   logger=logger,
                                   market=market,
                                   print_space=ps)
    if query is None:  # Failed to retrieve query
        return f'Failed: Could not form {source.name.capitalize()} query'

    # Skip if the path based on this file exists
    _, track_tags = source.sort_lookup(query, None)
    if file_from_tags_exists(track_tags, logger, avoid_duplicates):
        return 'Skipped: FileExists'

    # If the query contains this field it cannot be empty or zero.
    req_fields = ['duration', 'title', 'album', 'artist']
    if any([not bool(query[c]) for c in req_fields if c in query]):
        set_song_db(track_uri)
        return f'Failed: URL object is empty "{track_uri}"'

    # Match the object
    search = source.get_search_platform()
    match_obj = lookup(query=query,
                       platform=search,
                       logger=logger,
                       **kwargs)

    if match_obj is False:
        return f'Failed: Could not match {source.name.capitalize()} to ' \
               f'{search.name.capitalize()} item'

    track_uri, track_tags = source.sort_lookup(query, match_obj)
    tags_uri = get_tags_uri(track_tags)
    source_uri = source.url2uri(track_url)  # 1 id may >1 urls

    # 1) Check if the file, or a similar file does not exist already
    if file_from_tags_exists(track_tags, logger, avoid_duplicates):
        return 'Skipped: FileExists'

    #  2) Check if the found tracks is already in the database
    if not do_overwrite:
        song_db_indices = get_song_db().index
        ctrl = [('Tag', tags_uri), ('Track', track_uri), ('Source', source_uri)]
        errs = [err for err, idx in ctrl if idx in song_db_indices]
        if any(errs):
            return ' '.join(['Skipped:', *[f'{e}Exists' for e in errs]])

    # Define download settings
    kwg_df = pd.Series({k: kwargs[k.replace('_kwarg_', '')]
                        for k in song_db_template if k[:7] == '_kwarg_'})
    download_info = pd.concat([track_tags, kwg_df])

    # Set song database entries
    set_song_db(track_uri, download_info, overwrite=True)
    return f'Success: Download added "{track_uri}"', tags_uri, source_uri, track_uri


def match_audio_with_tags(track_url: str, **kwargs):
    """
    This function matches a given URL, and writes what it found to the song
    database, after which it calls this function again, but as a background
    process, and finishes.
    """
    ps = kwargs['print_space']

    # Create a logger object for this URL
    logger_path = log_dir.format(shorten_url(track_url))
    logger = Logger(logger_path, verbose=True)

    # Get the source platform module and the platform we need to match it with
    source = get_url_platform(track_url)
    if source is None:  # matching failed
        return f'UnknownPlatform "{track_url}"'
    else:
        logger(f'New {source.name} URL:'.ljust(ps), strip_url(track_url))

    search_result = do_match(track_url, source, logger, **kwargs)
    if isinstance(search_result, tuple):
        status, tags_uri, source_uri, track_uri = search_result
        set_song_db(tags_uri, overwrite=False)
        set_song_db(source_uri, overwrite=False)
    else:
        status = search_result
        track_uri = source.url2uri(track_url)
    set_song_db(track_uri, overwrite=False)

    status = status.split(':')
    logger(str(status[0] + ':').ljust(ps) + ':'.join(status[1:]) + '\n')


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

    url = platform.url_unshortner(url)
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
            if input_is('Help', input_url):
                with click.Context(click_processor) as ctx:
                    click.echo(click_processor.get_help(ctx))
            elif input_is('Params', input_url):
                for k, v in kwargs.items():
                    print(k.ljust(20), v)
            elif not input_url or input_is('Abort', input_url):
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
@click.option("-m", "--market", default=default_market,
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