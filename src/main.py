from initialize import log_dir, default_location
from utils import Logger, input_is, get_url_platform, shorten_url, \
    get_path_components, track_exists, sanitize_track_name, strip_url, flatten
from tag_manager import get_track_tags, manual_track_tags, get_tags_uri
import sys
import re
import index
from download_daemon import start_daemons
import click
from click import Choice
from typing import List
from difflib import SequenceMatcher
import unicodedata


def similar(a, b):
    # Returns a string similarity score between 0 and 1
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def compare_meta(*args) -> List[bool]:
    """
    Checks if the given track name and artist name are a clear match for a
    given title (case-, diacritic- and non-alphanumeric insensitive).

    :param args consists of pairs of values to be checked agaist each other
    :return: True if both the track name and artist name can be found in the
    title, otherwise False.
    :rtype: bool

    Example:
    > compare_meta(
    >     "Lose You To Love Me", "Lose You To Love Me (Official Music Video)",
    >     "Selena Gomez", "selena gomez",
    > )
    True
    """
    if len(args) % 2:
        raise ValueError('Incomplete pair in values to compare.')

    # Remove all non letter characters
    def strip(arg: str) -> str:
        # Normalize to remove accents
        # (NFKD normalization splits characters from diacritics)
        normalized = unicodedata.normalize('NFKD', arg.lower())
        # Remove alphanumeric characters
        return re.sub(r'\W+', '', normalized)

    matches = []
    for a, b in zip(*[args[0::2]] + [args[1::2]]):
        a_s = sanitize_track_name(a)
        b_s = sanitize_track_name(b)
        matches.append(strip(a_s) in strip(b_s) or strip(b_s) in strip(a_s))
    return matches


def lookup(query: dict, platform, logger: callable = print, sort_by='none',
           **kwargs) -> dict | None:
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

    :param sort_by: The name of the method by which results are sorted. The only
        implemented method is duration, but in the future, more fine grained
        methods could easily be implemented

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
    match = None  # This is what we will return

    # Sanitize default response
    accept_origin = 'the user' if default_response is None else 'default'

    # Query the desired platform
    search_query = f'{query["title"]} {query["artist"]}'
    qstr = search_query if len(search_query) < 53 else search_query[:50] + '...'
    logger(f'Searching {platform.name.capitalize()} for:'.ljust(ps), f'"{qstr}"'.ljust(50), "srt% tim% sim%")
    items = platform.search(search_query, **kwargs)

    # Check if one of our search results matches our query
    if not any(items):
        sorted_properies = []
        logger(f'No results found for {accept_origin} search.')
        if default_response is not None:
            default_response = 'Abort'
    else:
        # Define matching properties
        relative_duration = platform.t_extractor(*items, query_duration=query['duration'])
        duration_similarity = [1 - abs(d - 1) for d in relative_duration]
        # When we use YouTube as source...
        title_similarity = [similar(i['title'] if 'title' in i else '', query['title']) for i in items]
        combination = [d_sim * t_sim for d_sim, t_sim in zip(duration_similarity, title_similarity)]
        original_sorting = [i/(len(items)-1) for i in range(len(items))][::-1]

        # Specify the key to be sorted by
        sort_key = {
            'none': original_sorting,
            'duration': duration_similarity,
            'title': title_similarity,
            'combination': combination,
        }[sort_by]

        # Replace Nones
        sort_key = [0 if v is None else v for v in sort_key]
        sorted_properies = sorted(zip(
            sort_key,
            items,
            relative_duration,
            title_similarity,
        ), reverse=True)

    for n, (key, item, duration, similarity) in enumerate(sorted_properies, 1):
        # Extract information from our query result items
        item_title, item_artist = platform.item2desc(item)
        item_desc = f'{item_title} - {item_artist}'

        # Print a synopsis of our search result

        sim_strs = ' '.join([f'{v:.0%}'.rjust(4) for v in [key, duration, similarity]])
        key_str = f'{str(key)}%' if key is None else sim_strs
        logger(''.rjust(ps), f'{n}) {item_desc[:46].ljust(47)} {key_str}')

        # Check how the duration matches up with what we are looking for
        is_duration_match = None if duration is None else \
                abs(key - 1) < duration_tolerance

        is_meta_match = compare_meta(item_title, query["title"], item_artist, query["artist"])

        # Check if the search result is a match
        if all(is_meta_match) and is_duration_match:
            logger(f'Clear {platform.name} match:'.ljust(ps), f'{item_desc}')
            if platform.name == 'spotify':
                match = get_track_tags(item)
            else:
                breakpoint()
                match = {'track_uri': 'youtube.' + item['videoId'],
                         'title': item['title'],
                         'artist': item['artists'][0]['name'],
                         'duration': item['duration_seconds']}
            break

    # Without clear match provide the user with options:
    if match is None:
        no_match_status = f'No clear {platform.name} match. ' + '{}:'
        # Set appropriate response
        if default_response is not None:
            proceed = default_response
            logger(no_match_status.format(f'Default to {proceed}'))
        else:
            logger(no_match_status.format('Select'))
            if any(items):
                item_options = '/'.join([str(i + 1)
                                         for i in range(len(items))]) + '/'
                default = '1'
            else:
                item_options = ''
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
                if platform.name == 'spotify':
                    match = get_track_tags(items[idx])
                elif platform.name == 'youtube':
                    match = {
                        'track_uri': 'youtube.' + items[idx]['videoId'],
                        'album_artist': items[idx]['artists'][0]['name'],
                        'artist': platform.get_artist(items[idx]),
                        'title': items[idx]['title'],
                        'duration': items[idx]['duration_seconds'],
                    }
                item_desc = f'{match["title"]} - {match["artist"]}'
                logger(f'Match accepted by {accept_origin}: '
                       f''.ljust(ps), item_desc)

        elif input_is('Retry', proceed):
            logger(f'Provide new info for {platform.name} query: ')
            search_query = input('>>> Track name and artist? '
                                 ''.ljust(ps))
            query['title'] = search_query
            query['artist'] = ''

        elif input_is('Manual', proceed):
            if platform.name == 'spotify':
                logger('Provide manual track info: ')
                match = manual_track_tags(market=market,
                                          duration=query['duration'])
                match['internet_radio_url'] = 'manual'
            elif platform.name == 'youtube':
                match = input('>>> Provide YouTube URL: '
                                    ''.ljust(ps)).split('&')[0]

        elif input_is('Abort', proceed):
            match = False

        elif input_is('Change market', proceed):
            market = input('>>> Market code?'.ljust(ps)) or None
            logger('Market changed to:'.ljust(ps))
            kwargs['market'] = market
        else:
            logger(f'Invalid input "{proceed}"')

    # Give it another try with our updated arguments
    if match is None and default_response is None:
        match = lookup(
            query=query,
            platform=platform,
            logger=logger,
            **kwargs,
        )
    return match


def file_from_tags_exists(track_tags: dict | None, logger: callable = print, avoid_duplicates=True):
    if avoid_duplicates and track_tags is not None:
        artist_p, _, track_p = get_path_components(track_tags)
        if any(track_exists(artist_p, track_p, logger=logger)):
            return True
    return False


def do_match(track_url, source, logger: callable = print, **kwargs):
    """
        The do_match function handles the heavy lifting of the matching process.
        It is wrapped by match_audio_with_tags to enable harmonized handling of
        errors and creation of index items.
    """
    # Get the arguments
    market = kwargs['market']
    do_overwrite = kwargs['do_overwrite']
    avoid_duplicates = kwargs['avoid_duplicates']
    ps = kwargs['print_space']
    track_uri = source.url2uri(track_url)

    # Skip in case the URL is already in the database
    if index.has_uri(track_uri) and not do_overwrite:
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

    # Spotify's metadata of certain fields cannot be incomplete
    if source.name == 'spotify':
        req_fields = ['duration', 'title', 'album', 'artist']
        if any([not bool(query[c]) for c in req_fields if c in query]):
            index.write(track_uri)
            return f'Failed: Insufficient meta data to ' \
                   f'complete the processing of "{track_uri}".'

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
        # song_db_indices = sdb_get_uris()
        ctrl = [('Tag', tags_uri), ('Track', track_uri), ('Source', source_uri)]
        errs = [err for err, idx in ctrl if index.has_uri(idx)]
        if any(errs):
            return ' '.join(['Skipped:', *[f'{e}Exists' for e in errs]])

    # Set index items
    if tags_uri != 'manual':
        index.write(tags_uri)
    index.write(track_uri, tags=track_tags, settings=kwargs, overwrite=True)

    return f'Success: Download added.\n' \
           f'    -> TAG   {tags_uri}\n' \
           f'    -> AUDIO {track_uri}'


def match_audio_with_tags(track_url: str, **kwargs):
    """
    This function matches a given URL, and writes what it found to the song
    database, after which it calls this function again, but as a background
    process, and finishes.
    """
    ps = kwargs['print_space']

    # Create a logger object for this URL
    logger_path = log_dir.format(shorten_url(track_url), 'json')
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
        index.write(tags_uri, overwrite=False)
        index.write(source_uri, overwrite=False)
    else:
        status = search_result
        track_uri = source.url2uri(track_url)
    index.write(track_uri, overwrite=False)

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
        # url = url.split('?')[0]  # sanitization
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
@click.option("-m", "--market", default=default_location,
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
