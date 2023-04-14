import sys
import pandas as pd
import pytube
from time import sleep
from utils import spotify, Logger, input_is, get_url_domain, shorten_url, hms2s, log_dir, settings
from settings import print_space, default_market, default_tolerance, search_limit
from tag_manager import get_track_tags, manual_track_tags
import youtube
import soundcloud
from song_db import set_song_db, get_song_db
from download_daemon import start_daemon
from youtubesearchpython import VideosSearch
from unidecode import unidecode


def is_clear_match(track_name, artist_name, title):
    rip = lambda string: unidecode(string).lower()
    return rip(track_name) in rip(title) and rip(artist_name) in rip(title)


def lookup(query: pd.Series, platform: str, logger: Logger, duration_tolerance=0.05,
           market='NL', default_response=None, search_limit=5):
    # Set logging options
    logger_verbose_default = logger.verbose
    logger.verbose = True
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
        if hasattr(query, 'video_title'):  # Manual retries are set to this field
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
            results = spotify.search(q=search_query, market=market, limit=search_limit, type='track')
            items = results['tracks']['items']
        elif platform == 'youtube':
            results = VideosSearch(query=search_query, limit=search_limit).result()
            items = results['result']
    except KeyboardInterrupt:
        matched_obj = False
    except TimeoutError:  # Handling requests.exceptions.ReadTimeout errors from the spotify server
        logger('spotify encountered a Timeout error. Try again in 2 seconds.')
        sleep(2)

    # Check if one of our search results matches our query
    for n, item in enumerate(items, 1):
        # Extract information from our query results
        if platform == 'spotify':
            item_duration = item['duration_ms'] / 1000
            item_tags = get_track_tags(item, logger=logger, do_light=True)
            name = item_tags.title
            artist = item_tags.album_artist
            item_descriptor = f'{name} - {artist}'
        elif platform == 'youtube':
            item_duration = hms2s(item['duration'])
            item_descriptor = item['title']
            title = item['title']

        # Check how the duration matches up with what we are looking for
        relative_duration = query.duration / item_duration
        is_duration_match = abs(relative_duration - 1) < duration_tolerance

        # Print a synopsis of our search result
        logger(''.rjust(print_space), f'{n}) {item_descriptor[:40].ljust(40)} {relative_duration:.0%}')

        # Check if the search result is a match
        if is_clear_match(name, artist, title) and is_duration_match:
            logger(f'Clear {platform} match'.ljust(print_space), f'{item_descriptor}')
            if platform == 'spotify':
                matched_obj = get_track_tags(item, logger=logger, do_light=False)
            else:
                matched_obj = item['link']

    # Without clear match provide the user with options:
    if matched_obj is None:
        logger(f'No clear {platform} match. Select:')
        if default_response is None:
            item_options = '/'.join([str(i + 1) if i else f'[{i + 1}]' for i in range(len(items))])
            default = '1' if any(items) else 'Retry'
            proceed = input(f'>> {item_options}/Retry/Manual/Abort/Change market: ') or default
        else:
            proceed = default_response

        # Take action according to user input
        if proceed.isdigit():
            idx = int(proceed) - 1
            if idx > len(items):
                logger(f'Invalid index {idx} for {len(items)} options.')
            else:
                if platform == 'spotify':
                    matched_obj = get_track_tags(items[idx], logger=logger, do_light=False)
                    item_descriptor = f'{matched_obj.title} - {matched_obj.album_artist}'
                elif platform == 'youtube':
                    item = items[idx]
                    item_descriptor = item['title']
                    matched_obj = item['link']
                logger(f'Match accepted by {accept_origin}: '.ljust(print_space), item_descriptor)

        elif input_is('Retry', proceed):
            logger(f'Provide new info for {platform} query: ')
            search_query = input('>> Track name and artist? '.ljust(print_space))
            query.video_title = search_query

        elif input_is('Manual', proceed):
            if platform == 'spotify':
                logger('Provide manual track info: ')
                matched_obj = manual_track_tags(market=market)
            elif platform == 'youtube':
                matched_obj = input('Provide YouTube URL: '.ljust(print_space)).split('&')[0]

        elif input_is('Abort', proceed):
            logger('I\'m sorry :(')
            matched_obj = False

        elif input_is('Change market', proceed):
            market = input('>> Market code?'.ljust(print_space)) or None
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
    logger.verbose = logger_verbose_default
    return matched_obj


def match_audio_with_tags(track_url: str, logger: Logger, duration_tolerance=0.05, market='NL', default_response=None, search_limit=5):
    """
    This function matches a given URL, and writes what it found to the song database,
    after which it calls this function again, but as a background process, and finishes.
    """
    logger_verbose_default = logger.verbose
    logger.verbose = True

    # Get the information we need to perform the matching
    url_domain = get_url_domain(track_url)
    if url_domain == 'spotify':
        item = spotify.track(track_url, market=market)
        track_tags = get_track_tags(item, logger=logger, do_light=False)
        query = track_tags
        track_url = None
    else:
        if url_domain == 'youtube':
            module = youtube
        elif url_domain == 'soundcloud':
            module = soundcloud
        query = module.get_description(track_url, logger)
        track_tags = None

    # Perform matching and check results
    if query is None:
        logger('Failed to produce query for lookup.', verbose=True)
    else:
        matched_obj = lookup(query=query,
                            platform=url_domain,
                            logger=logger,
                            duration_tolerance=duration_tolerance,
                            market=market,
                            default_response=default_response,
                            search_limit=search_limit)
        if not matched_obj:
            logger('Failed to lookup track')
        elif url_domain == 'spotify':
            track_url = matched_obj
        else:
            track_tags = matched_obj

    # Store results or report error.
    if not track_tags:
        logger('Failed to produce dict of tags from Spotify lookup.\n', verbose=True)
    elif not track_url:
        logger(f'Failed to match YouTube video to Spotify query.\n', verbose=True)
    else:
        set_song_db(track_url, track_tags)
        logger('Successfully Created Song DB entry.\n', verbose=True)

    # Reset and return
    logger.verbose = logger_verbose_default
    return


def init_matching(*urls, default_response=None):
    for i, url in enumerate(urls):
        # Sanitize URL
        url = url.split('&')[0]

        # Identify the domain
        domain = get_url_domain(url)

        if 'playlist' in url:  # Handling of playlists
            if domain == 'youtube':
                playlist_urls = pytube.Playlist(url)
            elif domain == 'spotify':
                playlist_items = spotify.playlist(url.split('/')[-1])['tracks']['items']
                playlist_urls = [f"https://open.spotify.com/track/{t['track']['id']}" for t in playlist_items]
            do_playlist = input(f'Received playlist with {len(playlist_urls)} items. Proceed? [Yes]/No  '.ljust(print_space))
            if input_is('No', do_playlist):
                print('Playlist skipped.')
                continue
            elif input_is('Yes', do_playlist) or not do_playlist:
                default_response = input('Set default response procedure?: [None]/1/Abort  '.ljust(print_space)) or None
                if default_response is None:
                    pass
                elif input_is('None', default_response):
                    default_response = None
                elif not input_is('1', default_response) and not input_is('Abort', default_response):
                    print('Invalid input:'.ljust(print_space), f'"{default_response}"')
                    default_response = None
                init_matching(*playlist_urls, default_response=default_response)
            else:
                print('Invalid input:'.ljust(print_space), f'"{do_playlist}"')
        else:  # Handling of individual tracks
            if url in get_song_db():
                print('Track exists in Song Data Base. Skipped.\n')
                continue
            logger_path = log_dir.format(shorten_url(url))
            log_obj = Logger(logger_path)
            log_obj(f'{i}/{len(urls)} Received new {domain} URL'.ljust(print_space), url)
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
    """
    This script takes a YouTube URL, downloads the audio and adds mp3 tag data using the Spotify API

    Input:
        Whithout input it will start in Python mode (see below)
        Alternatively any number of Youtube Vidoe URLS or Public Playlist URLs are accepted

    This function calls itself as background process
        This sounds a bit convoluted, but it boosts performance greatly! It works in two steps:
        1) You provide the script with a YouTube URL for which it will get the title 
           (`yt_url2title`) which it will try to match by searching the Spotify data base
           (`spotify_lookup`) This will usually find a match, but in case it does not you provide 
           semi automatic oversight and will be prompted with options to proceeed. 
        2) The song has been matched and the hard work can begin in `pull_song`: 
           1. Define file and directory names
           2. Check if this song is already available for this artist.
           3. Download audio
           4. Download album cover image
           5. Set mp3 tags from Spotify meta data
           6. Fix directy ownership and potential access issues
           This might take 2 minutes. And you do not want to wait! So here is the fix:
           After the match, the song will write down the spotify meta data it found in the Song
           Data base (`song_db.pkl`). It will then call `main.py` again, but as a background 
           process, and the foreground process will finish. At the beginning of the main call of 
           the background process `get_track.`py` checks if the requested YouTube URL is already
           in the song data base, and if so, will not initiate the semi-automatic matching process,
           (`spotify_lookup`) but the downloading process described above (`pull_song`).

    Modes:
        This script can be run in Python mode, or Bash mode.
        In Python mode, you provide the URLs within Python using the `input` function, which can
        perform string sanitation. It then forwards the request to the Bash mode.
        In Bash mode you can directly send a URL to be processed. Just make sure the string has
        been sanitized (so no "&" symbols).

    Copyright and use:
        Audio you download using this script can not contain third-party intellectual property
        (such as copyrighted material) unless you have permission from that party or are otherwise 
        legally entitled to do so (including by way of any available exceptions or limitations to 
        copyright or related rights provided for in European Union law). You are legally 
        responsible for the Content you submit to the Service.     

    Maarten Poirot (www.maartenpoirot.com) March 2023
    """
    if len(sys.argv) == 1:  # No URL provided, run in Python mode
        while True:
            input_url = input('URL or [Abort]?'.ljust(print_space))
            if not input_url or input_is('Abort', input_url):
                print('Bye Bye!')
                sys.exit()
            else:
                init_matching(*input_url.split(' '))
    else:
        urls = sys.argv[1:]
        init_matching(*urls)


# os.system(f'sudo su plex -s /bin/bash')
# We will want to use the API for scanning:
# http://192.168.2.1:32400/library/sections/6/refresh?path=/srv/dev-disk-by-uuid-1806e0be-96d7-481c-afaa-90a97aca9f92/Plex/Music/Lazzo&X-Plex-Token=QV1zb_72YxRgL3Vv4_Ry
# print('you might want to run...')
# print(f"'/usr/lib/plexmediaserver/Plex\ Media\ Scanner --analyze -d '{root}'")

