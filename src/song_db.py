from __future__ import annotations

from initialize import song_db_path
from utils import input_is
from utils import json_out, json_in
from typing import List
from pathlib import Path
import json


song_db_template = {
    'tags': {
        'album': str,
        'album_artist': str,
        'artist': str,
        'bpm': int,
        'cover': str,
        'disc_max': int,
        'disc_num': int,
        'duration': float,
        'genre': str,
        'internet_radio_url': str,
        'release_date': str,
        'recording_date': str,
        'tagging_date': str,
        'title': str,
        'track_max': int,
        'track_num': int,
    },
    'settings': {
        'avoid_duplicates': bool,
        'do_overwrite': bool,
        'max_daemons': int,
        'print_space': int,
        'quality': int,
        'verbose': bool,
        'verbose_continuous': bool,
    },
}

def uri2path(uri: str | Path) -> Path:
    path = uri if isinstance(uri, Path) else song_db_path / uri
    return path


def sdb_has_uri(uri: str | Path) -> bool:
    return uri2path(uri).is_file()


# def sdb_get_uris() -> List[str]:
#     return [f.name for f in song_db_path.glob('*')]


def pretty_print(uri: str | Path) -> None:
    print(json.dumps(sdb_read(uri2path(uri)), indent=4, sort_keys=True))


def sdb_read(uri: str | Path) -> dict:
    path = uri2path(uri)
    return None if is_empty(path) else json_in(path)


def is_empty(path: Path) -> bool:
    return path.stat().st_size == 0


def sdb_to_do() -> List[str]:
    # This is a bit of a slow operation which I could improve in the future,
    # But it is not called frequently.
    # Returns a list of uris
    return [f.name for f in song_db_path.rglob("*") if not is_empty(f)]


def sdb_write(uri: str | Path | None, tags=None, settings=None, overwrite=True) -> None:
    """ Set a value to a key (=short URL) in the song database """
    if uri is None:  # Happens for manual entries
        return

    path = uri2path(uri)
    if not overwrite and sdb_has_uri(path):
        return
    payload = {'tags': tags, 'settings': settings}
    json_out(payload, path) if any(payload.values()) else open(path, 'w').close()


def pop_song_db(uri: str | Path) -> None:
    uri2path(uri).unlink()
    print(f'Deleted song database file "{uri}"')


def debug_song_db() -> None:
    # Get statistics of the song database
    n_records = len(list(song_db_path.glob('*')))
    to_do = sdb_to_do()
    n_to_do = len(to_do)
    n_empty_records = n_records - n_to_do

    # Structure the meta information to print
    info = [
        ('number of processed records', n_empty_records),
        ('number of unprocessed records', n_to_do),
        ('location', song_db_path),
    ]

    # Print header and the song dat base meta information
    print('SONG DATABASE INFORMATION:',
          *['\n- {}{}'.format(k.ljust(30), str(v).rjust(6)) for k, v in
            info]
          )

    # Give control to the user about
    if n_to_do:
        look_closer = input('>>> Do you want to see a list of items, '
                            'or check per item? List / Item / [No]  ')
        if input_is('List', look_closer) or input_is('Item', look_closer):
            for i, path in enumerate(to_do):
                print(f'{str(i + 1).rjust(3)}/{n_to_do}:', path.name)
                pretty_print(path)
                if input_is('Item', look_closer):
                    do_pop = input(
                        '>>> Do you want to permanently delete or clear this '
                        'item from the song data base? Delete / Clear / [No]  ')
                    if input_is('Delete', do_pop):
                        pop_song_db(path)
                        msg = 'deleted'
                    elif input_is('Clear', do_pop):
                        sdb_write(path)
                        msg = 'cleared'
                    else:
                        msg = 'untouched'
                    print(f'Song data base entry {msg}.')


if __name__ == '__main__':
    debug_song_db()
