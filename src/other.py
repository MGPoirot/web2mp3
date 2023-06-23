from pathlib import Path
from initialize import music_dir, default_market
from modules import spotify
from utils import rm_char, track_exists, timeout_handler, pickle_out, pickle_in
import os
from tag_manager import get_track_tags, set_file_tags
import eyed3

# Load progress
#music_dir = 'P:/Music'  # For windows
done_fname = 'done_files2.pkl'
if not os.path.isfile(done_fname):
    pickle_out([], done_fname)
done_files = [Path(music_dir, i) for i in pickle_in(done_fname)]


def update_file_tags():
    songs = list(Path(music_dir).glob('*/*/*.mp3'))
    for i, song in enumerate(songs):
        # Skip if already done
        if song in done_files:
            continue

        # Note progress
        if not i // 20:
            pickle_out([str(i.relative_to(music_dir)) for i in done_files], done_fname)
        done_files.append(song)
        print(f'{str(i).rjust(4)}/{len(songs)} ({i/len(songs):.0%})', song)

        # Check if this tag was already added but
        tags = eyed3.load(song).tag
        free_pass = False
        if tags.tagging_date is not None:
            if tags.tagging_date.month >= 6:
                continue

        # Get file tags to compare our metadata to
        if tags.title is not None:
            title = tags.title
            album = tags.album
            if tags.album_artist is not None:
                artist = tags.album_artist
            else:
                artist = tags.artist
        else:
            artist, album, title = str(song).split(os.sep)[-3:]
            title = title.split(os.extsep)[0].split(' - ')[1]

        # Get metadata, preferably by URL
        if tags.internet_radio_url is not None:
            tag_series = get_track_tags(timeout_handler(
                func=spotify.spotify_api.track,
                track_id=tags.internet_radio_url)
            )
        else:  # Otherwise by search
            for search_query in [f'track:{title} album:{album} artist:{artist}',
                      f'{title} {album} {artist}',
                      f'{title} {artist}']:
                finding = timeout_handler(
                    func=spotify.search,
                    search_query=search_query,
                    search_limit=1,
                    market='NL',
                )
                if any(finding):
                    break
            if not any(finding):
                continue
            tag_series = get_track_tags(finding[0])

        # If file tag data and metadata agree, update the tags
        if tag_series.album_artist == artist and\
                tag_series.title == title and\
                tag_series.album == album:
            audio_source_url = tags.audio_source_url if tags.audio_source_url is not None else 'Unknown'
            set_file_tags(tag_series, song, audio_source_url)


def file_has_duplicate():
    path = Path('P:/Music')
    songs = list(path.glob('*/*/*.mp3'))
    for i, song in enumerate(tqdm(songs)):
        tags = eyed3.load(song).tag
        artist = tags.album_artist if tags.album_artist is not None else tags.artist
        artist_p, track_p = rm_char(artist), rm_char(tags.title)
        existing_tracks = track_exists(artist_p, track_p, lambda *x: _)
        if any(existing_tracks):
            print(artist_p, track_p, '-->', *existing_tracks)

if __name__ == '__main__':
    update_file_tags()