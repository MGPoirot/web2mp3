import os
from dotenv import load_dotenv
load_dotenv()
from youtubesearchpython import VideosSearch
import sys
import pandas as pd
import pytube
from time import sleep
from utils import print_space, spotify, Logger, input_is
from song_db import get_song_db, set_song_db
from tag_manager import get_track_tags, manual_track_tags
from yt2mp3 import yt_download


def yt_url2title(youtube_url: str, logger: Logger) -> str:
    """
    Receives the link to a YouTube or YouTube Music video and returns the title
    :param logger:
    :param youtube_url: URL as string
    :logger logging object:
    :return: title as string
    """
    # Get video title
    yt_search_result = VideosSearch(youtube_url, limit=1).result()
    if not any(yt_search_result['result']):
        logger(f'ValueError: No video found for "{youtube_url}"', verbose=True)
        return None
    video_title = yt_search_result['result'][0]['title']
    uploader_id = yt_search_result['result'][0]['channel']['name']
    if uploader_id not in video_title:
        video_title += f' - {uploader_id}'
    return video_title


def sc_url2title(soundcloud_url: str, logger: Logger) -> str:
    raise NotImplementedError('Soundcloud API connection has not been implemented yet')


def spotify_lookup(spotify_query: str, logger: Logger, market='NL') -> pd.Series:
    while True:
        # Check the first 5 search result for a clear match
        logger('Searching Spotify for'.ljust(print_space), f'"{spotify_query}"', verbose=True)
        
        results = None
        are_screwed_over = False
        while results is None:
            try:
                results = spotify.search(q=spotify_query, market=market, limit=5, type='track')
            except KeyboardInterrupt:
                return
            except TimeoutError:
                if not are_screwed_over:
                    # TODO: Add requests_timeout parameter
                    logger('We are being screwed over by SpotiPy throtteling...', verbose=True)
                    are_screwed_over = True
                sleep(2)
                pass

        items = results['tracks']['items']
        for n, item in enumerate(items, 1):
            t = get_track_tags(item, do_light=True)
            logger(''.rjust(print_space), f'{n}) {t.title} - {t.album_artist}', verbose=True)
            # Check if the search result is a match
            if t.title.lower() in spotify_query.lower() and t.album_artist.lower() in spotify_query.lower():
                t = get_track_tags(item, do_light=False)
                logger('Clear Spotify match'.ljust(print_space), f'{t.title} - {t.album} - {t.album_artist}', verbose=True)
                return t

        # Without clear match provide the user with four options:
        try:
            logger('NO clear Spotify match. Select:', verbose=True)
            proceed = input(f'>> [1]/2/3/4/5/Retry/Manual/Abort/Change market: ') or '1'
        except IndexError:
            logger('Query did not return any results', verbose=True)
            proceed = input(f'>> Retry/Manual/Abort/Change market:') or 'Retry'

        # Take action according to user input
        if proceed.isdigit():
            t = get_track_tags(items[int(proceed) - 1], do_light=False)
            logger('Match accepted by user'.ljust(print_space), f'{t.title} - {t.album} - {t.album_artist}', verbose=True)
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
            return spotify_lookup(spotify_query, market=new_market, logger=logger)
        else:
            logger(f'Invalid input "{proceed}"')


def match_url_to_spotify(track_url: str, logger: Logger, market='NL'):
    """
    This function matches a given YouTube URL, and writes what it found to the song database,
    after which it calls this function again, but as a background process, and finishes.
    """
    # TODO: implement test if the URL is a YouTube or any other URL
    url_type = 'youtube'

    title_method = False
    if url_type == 'youtube':
        title_method = yt_url2title
    elif url_type == 'soundcloud':
        title_method = sc_url2title
    elif url_type == 'spotify':
        item = spotify.track(track_url, market=market)[0]
        track_tags = get_track_tags(item, do_light=False)
        # TODO: implement a YouTube lookup, and call pull_song with the YouTube URL
        pass
    else:
        raise ValueError(f'Unrecognized URL type: "{url_type}"')

    if title_method:
        # Find match
        sp_query = title_method(track_url, logger=logger)
        if sp_query is None:
            logger(f'Lookup of a "{url_type}" URL did not return a query for Spotify.')
            logger.close()
            return

        track_tags = spotify_lookup(sp_query, logger=logger)
        if track_tags is None:
            logger('Spotify lookup did not return a dict of tags')
            logger.close()
            return

    # Write match to song database entry
    set_song_db(track_url, track_tags)
    logger('Created Song DB entry')
    
    # Commence background process
    # TODO: dont call this fuction, but call a manager
    command = f"nice -n 19 nohup sudo python main.py {track_url} > /dev/null 2>&1 &"
    logger(command)
    os.system(command)
    logger.close()
    return


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
            yt_url = input('YouTube URL or [Abort]?'.ljust(print_space))
            if not yt_url or input_is('Abort', yt_url):
                print('Bye Bye!')
                sys.exit()
            yt_url = yt_url.split('&')[0]
            os.system(f'sudo python main.py {yt_url}')
    else:  # One or more URLs provided, 
        # Get the YouTube URI
        yt_urls = sys.argv[1:]
        song_db = get_song_db()
        for i, yt_url in enumerate(yt_urls):
            log_obj = Logger(yt_url, owner='get_track')
            if 'playlist' in yt_url:
                playlist_urls = pytube.Playlist(yt_url)
                do_playlist = input(f'Received playlist with {len(playlist_urls)} items. Proceed? [Yes]/No  ')
                if input_is('No', do_playlist):
                    print('Playlist skipped.')
                    continue
                elif input_is('Yes', do_playlist) or not do_playlist:
                    os.system(f'sudo nice -n 1 python main.py {" ".join(playlist_urls)}')
                else:
                    print('Invalid input:'.ljust(print_space), f'"{do_playlist}"')
            elif yt_url in song_db:
                if song_db[yt_url] is not None:
                    yt_download(yt_url, logger=log_obj)
            else:
                log_obj(f'{i}/{len(yt_urls)} Received new Youtube URL'.ljust(print_space), yt_url)
                match_url_to_spotify(yt_url, logger=log_obj)

# os.system(f'sudo su plex -s /bin/bash')
# We will want to use the API for scanning:
# http://192.168.2.1:32400/library/sections/6/refresh?path=/srv/dev-disk-by-uuid-1806e0be-96d7-481c-afaa-90a97aca9f92/Plex/Music/Lazzo&X-Plex-Token=QV1zb_72YxRgL3Vv4_Ry
# print('you might want to run...')
# print(f"'/usr/lib/plexmediaserver/Plex\ Media\ Scanner --analyze -d '{root}'")
