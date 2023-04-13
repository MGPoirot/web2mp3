import sys
import pandas as pd
import pytube
from time import sleep
from utils import spotify, Logger, input_is, get_url_domain, shorten_url, hms2s, log_dir, settings
from settings import print_space, default_market, default_tolerance
from tag_manager import get_track_tags, manual_track_tags
import youtube
import soundcloud
from song_db import set_song_db, get_song_db
from download_daemon import start_daemon
from youtubesearchpython import VideosSearch


def is_clear_match(track_name, artist_name, title):
    if track_name.lower() in title.lower() and artist_name.lower() in title.lower():
        return True
    else:
        return False


def spotify_lookup(spotify_query: str, audio_duration: int, logger: Logger, duration_tolerance=0.05,
                   market='NL', default_response=None, search_limit=5) -> pd.Series:
    accept_origin = 'the user' if default_response is None else 'default'
    if isinstance(default_response, str):
        if default_response.isdigit():
            search_limit = int(default_response)

    while True:
        # Check the first 5 search result for a clear match
        logger('Searching Spotify for'.ljust(print_space), f'"{spotify_query}"', verbose=True)
        
        results = None
        read_timeout = False

        while results is None:
            try:
                results = spotify.search(q=spotify_query, market=market, limit=search_limit, type='track')
            except KeyboardInterrupt:
                return
            except TimeoutError:  # Handling requests.exceptions.ReadTimeout errors from the spotify server
                if not read_timeout:
                    logger('spotify_lookup encountered a SpotiPy API ReadTimeout error', verbose=True)
                    read_timeout = True
                else:
                    logger('spotify_lookup failed after a SpotiPy API ReadTimeout error', verbose=True)
                    return
                sleep(2)
                pass

        items = results['tracks']['items']
        for n, item in enumerate(items, 1):
            t = get_track_tags(item, logger=logger, do_light=True)
            spotify_duration = item['duration_ms'] / 1000
            relative_duration = audio_duration / spotify_duration
            if abs(relative_duration - 1) > duration_tolerance:
                logger(f'Audio duration mismatch: {relative_duration:.1%} (YT/Sp)')
                continue
            logger(''.rjust(print_space), f'{n}) {t.title} - {t.album_artist}', verbose=True)
            # Check if the search result is a match
            if is_clear_match(t.title, t.album_artist, spotify_query):
                t = get_track_tags(item, logger=logger, do_light=False)
                logger('Clear Spotify match'.ljust(print_space),
                       f'{t.title} - {t.album} - {t.album_artist}', verbose=True)
                return t

        # Without clear match provide the user with four options:
        try:
            logger('NO clear Spotify match. Select:', verbose=True)
            if default_response is None:
                proceed = input(f'>> [1]/2/3/4/5/Retry/Manual/Abort/Change market: ') or '1'
            else:
                proceed = default_response
        except IndexError:
            logger('Query did not return any results', verbose=True)
            if default_response is None:
                proceed = input(f'>> Retry/Manual/Abort/Change market:') or 'Retry'
            else:
                proceed = default_response

        # Take action according to user input
        if proceed.isdigit():
            t = get_track_tags(items[int(proceed) - 1], logger=logger, do_light=False)
            logger(f'Match accepted by {accept_origin}'.ljust(print_space),
                   f'{t.title} - {t.album} - {t.album_artist}', verbose=True)
            return t
        elif input_is('Retry', proceed):
            logger('Provide new info for Spotify query', verbose=True)
            spotify_query = input('>> Track name and artist?'.ljust(print_space))
        elif input_is('Manual', proceed):
            logger('Provide manual track info', verbose=True)
            t = manual_track_tags(market=market)
            return t
        elif input_is('Abort', proceed):
            logger('I\'m sorry :(', verbose=True)
            return None
        elif input_is('Change market', proceed):
            new_market = input('>> Market code?'.ljust(print_space)) or None
            logger('Market changed to:'.ljust(print_space), verbose=True)
            return spotify_lookup(spotify_query, audio_duration, logger, duration_tolerance,
                                  new_market, default_response, search_limit)
        else:
            logger(f'Invalid input "{proceed}"')
            if default_response is not None:
                return


def youtube_lookup(track_tags: pd.Series, audio_duration: float, logger: Logger, duration_tolerance=0.05,
                   default_response=None, search_limit=5):
    youtube_query = f'{track_tags.title} - {track_tags.artist}'
    logger('Searching YouTube for'.ljust(print_space), youtube_query, verbose=True)
    yt_search_result = VideosSearch(youtube_query, limit=search_limit).result()['result']
    youtube_url = None
    for search_result in yt_search_result:
        youtube_duration = hms2s(search_result['duration'])
        relative_duration = youtube_duration / audio_duration
        if abs(relative_duration - 1) > duration_tolerance:
            logger(f'Audio duration mismatch: {relative_duration:.1%} (YT/Sp)')
            continue

        elif is_clear_match(track_tags.title, track_tags.album_artist, search_result['title']):
            logger('Clear YouTube match'.ljust(print_space), search_result['title'], verbose=True)
            youtube_url = search_result['link']
            break
    return youtube_url


def match_audio_with_tags(track_url: str, logger: Logger, market='NL', default_response=None, search_limit=5, duration_tolerance=0.05):
    """
    This function matches a given YouTube URL, and writes what it found to the song database,
    after which it calls this function again, but as a background process, and finishes.
    """
    url_domain = get_url_domain(track_url)
    if url_domain == 'spotify':
        item = spotify.track(track_url, market=market)
        spotify_duration = item['duration_ms'] / 1000
        track_tags = get_track_tags(item, logger=logger, do_light=False)
        youtube_url = youtube_lookup(track_tags, spotify_duration, logger, duration_tolerance, default_response, search_limit)
        track_url = youtube_url
    else:
        if url_domain == 'youtube':
            module = youtube
        elif url_domain == 'soundcloud':
            module = soundcloud
        # Find match
        sp_query, audio_duration = module.get_description(track_url, logger)
        if sp_query is None:
            logger(f'Lookup of a "{url_domain}" URL did not return a query for Spotify.')
            return

        track_tags = spotify_lookup(spotify_query=sp_query,
                                    audio_duration=audio_duration,
                                    logger=logger,
                                    duration_tolerance=default_tolerance,
                                    market=default_market,
                                    default_response=default_response,
                                    search_limit=search_limit)
    if track_tags is None:
        logger('Failed to produce dict of tags from Spotify lookup.\n', verbose=True)
        return
    elif track_url is None:
        logger(f'Failed to match YouTube video to Spotify query.\n', verbose=True)
        return

    # Write match to song database entry
    set_song_db(track_url, track_tags)
    logger('Successfully Created Song DB entry.\n', verbose=True)
    
    # Commence background process
    return


def init_matching(*urls, default_response=None):
    for i, url in enumerate(urls):
        url = url.split('&')[0]
        # identiy the domain
        domain = get_url_domain(url)
        if 'playlist' in url:
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
        else:
            if url in get_song_db():
                continue
            logger_path = log_dir.format(shorten_url(url))
            log_obj = Logger(logger_path)
            log_obj(f'{i}/{len(urls)} Received new {domain} URL'.ljust(print_space), url)
            match_audio_with_tags(url, logger=log_obj, default_response=default_response)
        start_daemon()

# os.system(f'sudo su plex -s /bin/bash')
# We will want to use the API for scanning:
# http://192.168.2.1:32400/library/sections/6/refresh?path=/srv/dev-disk-by-uuid-1806e0be-96d7-481c-afaa-90a97aca9f92/Plex/Music/Lazzo&X-Plex-Token=QV1zb_72YxRgL3Vv4_Ry
# print('you might want to run...')
# print(f"'/usr/lib/plexmediaserver/Plex\ Media\ Scanner --analyze -d '{root}'")


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
            # TODO Allow for multiple arguments: default response value
            input_url = input('URL or [Abort]?'.ljust(print_space))
            if not input_url or input_is('Abort', input_url):
                print('Bye Bye!')
                sys.exit()
            else:
                init_matching(*input_url.split(' '))
    else:
        urls = sys.argv[1:]
        init_matching(*urls)
