from initialize import song_db_file
from utils import input_is
import pandas as pd
import os
import shutil
from pandas import Int64Dtype as PdInt
from pandas import BooleanDtype as PdBool
from pandas import StringDtype as PdStr
from pandas import Float32Dtype as PdFlt
from time import time as now
from time import sleep

song_db_template = {
    'album': PdStr(),
    'album_artist': PdStr(),
    'artist': PdStr(),
    'bpm': PdInt(),
    'cover': PdStr(),
    'disc_max': PdInt(),
    'disc_num': PdInt(),
    'duration': PdFlt(),
    'genre': PdStr(),
    'internet_radio_url': PdStr(),
    'release_date': PdStr(),
    'recording_date': PdStr(),
    'tagging_date': PdStr(),
    'title': PdStr(),
    'track_max': PdInt(),
    'track_num': PdInt(),
    '_kwarg_avoid_duplicates': PdBool(),
    '_kwarg_do_overwrite': PdBool(),
    '_kwarg_max_daemons': PdInt(),
    '_kwarg_print_space': PdInt(),
    '_kwarg_quality': PdInt(),
    '_kwarg_verbose': PdBool(),
    '_kwarg_verbose_continuous': PdBool(),
}

sdb_path = song_db_file.format('')
tmp_path = song_db_file.format('.')


def repair_sdb(verbose=True) -> None:
    # Creates a song database from a copy
    if verbose:
        print('The song database was corrupted. Loading from backup.')
    shutil.copy(tmp_path, sdb_path)


def get_song_db(columns=None) -> pd.DataFrame:
    """
    Load the Song Database (song_db) file, or
    create one if it does not exist.
    The song_db is used to store song properties for them to be processed and
    URLs of past processes in order to avoid processing them twice.
    """

    # Load the song database if it exists
    if not os.path.isfile(sdb_path):
        sdb = pd.DataFrame(columns=list(song_db_template)).astype(
            song_db_template)
        sdb.to_parquet(sdb_path)
    try:
        # Test if the file can be loaded
        sdb = pd.read_parquet(sdb_path, columns=columns)
    except:  # OSError, but also cramjam.DecompressionError
        repair_sdb()
        sleep(0.3)
        return get_song_db(columns=columns)

    # Every minute we also store a backup
    if all([c in sdb for c in song_db_template]):
        if not os.path.isfile(tmp_path) or now() - os.stat(
                sdb_path).st_mtime > 60:
            sdb.to_parquet(tmp_path)
    return sdb


def set_song_db(uri: str, value=None, overwrite=True) -> None:
    """ Set a value to a key (=short URL) in the song database """
    if uri is None:
        # This can happen when the track_url is
        # None because tags were created manually.
        return

    if uri in get_song_db(columns=[]).index and not overwrite:
        return

    # Append the uri-value pair to the data frame.
    if value is None:
        # If no value is provided, create an empty DataFrame
        entry = pd.DataFrame(
            columns=list(song_db_template),
            index=[uri]
        ).astype(song_db_template)
    else:
        # Convert the pd.Series to a pd.DataFrame
        entry = value.to_frame(uri).T.astype(song_db_template)

    # Add entry and avoid duplicates
    sdb = get_song_db()
    sdb = pd.concat([sdb, entry])
    sdb = sdb[~sdb.index.duplicated(keep='last')]
    if not sdb.shape[0]:
        breakpoint()
    sdb.to_parquet(song_db_file.format(''))


def pop_song_db(uri: str) -> None:
    """ remove entry from song database"""
    sdb = get_song_db()
    item = sdb.loc[uri]
    print(
        f'Deleted song database entry "{item.title}" by "{item.album_artist}" ({uri})')
    get_song_db().drop(uri).to_parquet(song_db_file.format(''))


def debug_song_db() -> None:
    repair_sdb(verbose=False)

    # Time a full load
    then = now()
    sdb = get_song_db()
    full_duration = now() - then

    # Time an index load
    then = now()
    _ = get_song_db(columns=[])
    shrt_duration = now() - then

    # Get statistics of the song database
    n_records = len(sdb)
    to_do = sdb.title.notna()
    n_to_do = to_do.sum()
    n_empty_records = n_records - n_to_do
    backup_exists = os.path.isfile(tmp_path)
    backup_exists = 'exists' if backup_exists else 'does not exist'

    # Structure the meta information to print
    info = [
        ('number of processed records', n_empty_records),
        ('number of unprocessed records', n_to_do),
        ('Index loading time', f'{shrt_duration:.3f}s'),
        ('Full loading time', f'{full_duration:.3f}s'),
        ('location', sdb_path),
        ('backup', backup_exists)
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
            for i, (uri, record) in enumerate(sdb[to_do].iterrows()):
                print(f'{str(i + 1).rjust(3)}/{n_to_do}:', uri)
                print(record)
                if input_is('Item', look_closer):
                    do_pop = input(
                        '>>> Do you want to permanently delete this item '
                        'from the pending records? Yes / [No]  ')
                    if input_is('Yes', do_pop):
                        pop_song_db(uri)
                        print('Deleted.')
                    else:
                        print('Not deleted.')


if __name__ == '__main__':
    debug_song_db()
