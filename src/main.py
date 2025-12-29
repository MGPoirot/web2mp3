from initialize import log_dir, default_location
import logging
from logging_setup import configure_logger, close_logger_handlers
from utils import input_is, get_url_platform, shorten_url, \
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
from typing import Iterable, Iterator


def similarity_str(sim_score: float | None) -> str:
    return ' N/A' if sim_score is None else f'{sim_score:.0%}'.rjust(4)


def title_similarity(a: dict, b: dict) -> float | None:
    """
    Computes the similarity score between the titles of two dictionaries
    using a sequence matching algorithm.

    :param a: A dictionary containing a 'title' key with a string value.
    :param b: Another dictionary containing a 'title' key with a string value.
    :return: A similarity score between 0 and 1, where 1 indicates a perfect
             match. Returns `None` if either dictionary lacks a 'title' key.
    :rtype: float | None
    """
    if 'title' not in a or 'title' not in b or a['title'] is None or b['title'] is None:
        return None
    return SequenceMatcher(None, a['title'].lower(), b['title'].lower()).ratio()


def duration_similarity(relative_d: float | None) -> float | None:
    """
    Calculates a duration similarity score based on the relative duration
    of a track compared to a target's duration.

    :param relative_d: The relative duration of the track compared to the
                       target's duration. This should be a positive value
                       or `None`.
    :return: A similarity score ranging from 1 (perfect match) to 0, or
             `None` if the input is `None`.
    :rtype: float | None
    """
    return None if relative_d is None else 1 - abs(relative_d - 1)


def similarity_mult(a: float | None, b: float | None) -> float | None:
    """
    Multiplies two similarity scores, returning None if either input is None.

    :param a: The first similarity score (float or None).
    :param b: The second similarity score (float or None).
    :return: The product of the two scores or None if either input is None.
    :rtype: float | None
    """
    if a is None or b is None:
        return None
    return a * b




def compare_meta(*args: str | None) -> bool:
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
        if a is None or b is None:
            matches.append(False)
        else:
            a_s = sanitize_track_name(a)
            b_s = sanitize_track_name(b)
            matches.append(strip(a_s) in strip(b_s) or strip(b_s) in strip(a_s))
    return all(matches)


def lookup(query: dict, platform, logger: callable = print, sort_by='none',
           **kwargs) -> dict | bool | None:
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

    # This is what we will return
    match = None

    # Extract properties that we will try to find a match to
    target_duration = query['duration']
    target_title = query["title"]
    target_artist = query["artist"]

    # Sanitize default response
    accept_origin = 'the user' if default_response is None else 'default'

    # Query the desired platform
    search_query = f'{query["title"]} {query["artist"]}'
    qstr = search_query if len(search_query) < 47 else search_query[:44] + '...'
    logger.info('%s "%s" %s', f'Searching {platform.name.capitalize()} for:'.ljust(ps), qstr, 'srt% tim% sim%')
    items = platform.search(search_query, **kwargs)

    # Check if one of our search results matches our query
    if not any(items):
        logger.info(f'No results found for {accept_origin} search.')
        return False

    # Check if essential fields are present
    # We do not discard invalid items, but they will score badly
    valid_items = platform.validate_items(items)

    # Tracks for which fields are missing or None are not valid options.
    if not any(valid_items):
        logger.info(f'No valid results found for {accept_origin} search.')
        return False

    # Read properties that we can use to find a match: 1) original soring,
    # 2) Duration, 3) Title, 4) a combination of duration and title.
    # This was primarily useful when I had not implemented YTMusic API, and 
    # I used the standard YouTube search sorting, which needed fine tuning to
    # provide the best matches to Spotify tracks; but it is still useful to 
    # validate the matching accuracy.

    # Normalize sorting to [0, 1]
    n = len(items)
    if n <= 1:
        original_sorting = [1.0] * n
    else:
        original_sorting = [1.0 - (i / (n - 1)) for i in range(n)]

    # Normalize duration similarity to [0, 1]
    relative_d = platform.t_extractor(*items, query_duration=target_duration)
    d_similarity = [duration_similarity(d) for d in relative_d]

    # Compute title similarity to [0, 1]
    t_similarity = [title_similarity(i, query) for i in items]

    # Compute a combination similarity score
    combination = [similarity_mult(*s) for s in zip(d_similarity, t_similarity)]

    # Specify the key to be sorted by
    sort_key = {
        'none': original_sorting,
        'duration': d_similarity,
        'title': t_similarity,
        'combination': combination,
    }[sort_by]

    # Replace Nones
    sort_key = [0 if v is None else v for v in sort_key]
    sorted_properties = sorted(zip(
        sort_key,
        items,
        relative_d,
        t_similarity,
    ), reverse=True)

    # Print a list of each option
    for n, (key, item, duration, similarity) in enumerate(sorted_properties, 1):
        # Extract information from our query result items
        item_title, item_artist = platform.item2desc(item)
        tit_art = f'{item_title} - {item_artist}'

        # Print a synopsis of our search result
        n_str = n if n in valid_items else 'X'
        similarity_scores = (key, duration, similarity)
        sim_strs = ' '.join([similarity_str(v) for v in similarity_scores])
        logger.info('%s %s', ''.rjust(ps), f'{n_str}) {tit_art[:46].ljust(47)} {sim_strs}')

        # Check if the item's duration difference from the target is acceptable
        is_duration_match = abs(key - 1) < duration_tolerance and bool(duration)
        # Check if the item's title and album match the target's
        is_meta_match = compare_meta(
            item_title, target_title,
            item_artist, target_artist,
        )

        # Check if the search result is a match
        if is_meta_match and is_duration_match:
            logger.info('%s %s', f'Clear {platform.name} match:'.ljust(ps), tit_art)
            match = platform.get_meta_info(item)
            break

    # Without clear match provide the user with options:
    if match is None:
        no_match_status = f'No clear {platform.name} match. ' + '{}:'
        # Set appropriate response
        if default_response is not None:
            proceed = default_response
            logger.info(no_match_status.format(f'Default to {proceed}'))
        else:
            logger.info(no_match_status.format('Select'))
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
            proceed = int(proceed)
            # Skip invalid options
            while proceed not in valid_items:
                proceed += 1
            idx = proceed - 1
            if idx > len(items) or idx < 0:
                logger.info(f'Invalid index {idx + 1} for {len(items)} options.')
            else:
                match = platform.get_meta_info(items[idx])
                tit_art = f'{match["title"]} - {match["artist"]}'
                logger.info('%s %s', f'Match accepted by {accept_origin}:'.ljust(ps), tit_art)

        elif input_is('Retry', proceed):
            logger.info(f'Provide new info for {platform.name} query: ')
            search_query = input('>>> Track name and artist? '
                                 ''.ljust(ps))
            query['title'] = search_query
            query['artist'] = ''

        elif input_is('Manual', proceed):
            match = platform.manual_handler(market=market, duration=duration)

        elif input_is('Abort', proceed):
            match = False

        elif input_is('Change market', proceed):
            market = input('>>> Market code?'.ljust(ps)) or None
            logger.info('Market changed to:'.ljust(ps))
            kwargs['market'] = market
        else:
            logger.info(f'Invalid input "{proceed}"')

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
    track_uri = source.url2uri(track_url)

    # Skip in case the URL is already in the index
    if index.has_uri(track_uri) and not do_overwrite:
        return f'Skipped: TrackExists "{track_uri}"'

    # Get a description of the object to use for matching.
    # IMPORTANT: forward CLI/runtime kwargs (e.g. max_time_outs) to the source.
    # Some sources (notably Spotify) rely on these for retry/throttle handling.
    query = source.get_description(track_url=track_url, logger=logger, **kwargs)
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

    # 1) Check if the file, or a title_similarity file does not exist already
    if file_from_tags_exists(track_tags, logger, avoid_duplicates):
        return 'Skipped: FileExists'

    #  2) Check if the found tracks is already in the index
    if not do_overwrite:
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
    This function matches a given URL, and writes what it found to the index
    after which it calls this function again, but as a background process,
    and finishes.
    """
    ps = kwargs['print_space']

    logger_path = log_dir.format(shorten_url(track_url), 'json')
    logger = configure_logger(
        name=f"web2mp3.match.{shorten_url(track_url)}",
        log_file=logger_path,
        console=not kwargs.get('headless', False),
    )

    try:
        # Get the source platform module and the platform we need to match it with
        source = get_url_platform(track_url)
        if source is None:  # matching failed
            return f'UnknownPlatform "{track_url}"'
        else:
            logger.info('%s %s', f'New {source.name} URL:'.ljust(ps), strip_url(track_url))
        
        search_result = do_match(track_url, source, logger, **kwargs)
        if isinstance(search_result, tuple):
            status, tags_uri, source_uri, track_uri = search_result
            index.write(tags_uri, overwrite=False)
            index.write(source_uri, overwrite=False)
        else:
            status = search_result
            track_uri = source.url2uri(track_url)

        # Only clear an existing index entry.
        # On failures that happen *before* an index item is created (e.g. Spotify
        # throttling leading to "Failed: Could not form Spotify query"), we must
        # NOT create an empty marker file, as that incorrectly signals completion.
        if index.has_uri(track_uri):
            index.write(track_uri, overwrite=False)

        # Nicely format any status string
        status = status.split(':')
        logger.info(str(status[0] + ':').ljust(ps) + ':'.join(status[1:]) + '\n')
    finally:
        # Critical: release the per-URL log file handle(s).
        close_logger_handlers(logger)

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


def iter_unpacked_urls(urls: Iterable[str]) -> Iterator[str]:
    for u in urls:
        for x in unpack_url(u):
            yield x


def main(**kwargs):
    # Get arguments
    ps = kwargs['print_space']
    raw_urls = kwargs['urls']
    init_daemons = kwargs['init_daemons']
    headless = kwargs['headless']
    max_daemons = kwargs['max_daemons']
    verbose = kwargs['verbose']

    # Unpack URLs that contain playlists or albums
    for url in iter_unpacked_urls(raw_urls):
        # Sanitization
        # url = url.split('?')[0]
        # Do not pass the content of an entire playlist but just the specific track
        kwargs['urls'] = url
        # Match audio and tags and write it to a file in the index
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
