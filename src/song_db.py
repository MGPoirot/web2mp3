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


def get_song_db() -> pd.DataFrame:
    """
    Load the Song Data Base (song_db) file, or
    create one if it does not exist.
    The song_db is used to store song properties for them to be processed and
    URLs of past processes in order to avoid processing them twice.
    """
    # Load the song database is it exists
    if not os.path.isfile(sdb_path):
        sdb = pd.DataFrame(columns=song_db_template).astype(song_db_template)
        sdb.to_parquet(sdb_path)
    try:
        # Test if the file can be loaded
        sdb = pd.read_parquet(sdb_path)
    except:  #OSError, but also cramjam.DecompressionError
        print('The song data base was corrupted. Loading from backup.')
        shutil.copy(tmp_path, sdb_path)
        sdb = pd.read_parquet(sdb_path)

    # Evert minute we also store a backup
    if not os.path.isfile(tmp_path):
        sdb.to_parquet(tmp_path)
    elif now() - os.stat(sdb_path).st_mtime > 60:
        sdb.to_parquet(tmp_path)
    return sdb


def set_song_db(uri: str, value=None, overwrite=True):
    """ Set a value to a key (=short URL) in the song database """
    if uri is None:
        # This can happen when the track_url is
        # None because tags were created manually.
        return

    song_db = get_song_db()
    if uri in song_db.index and not overwrite:
        return

    if value is None:
        entry = pd.DataFrame(columns=song_db_template, index=[uri]).astype(song_db_template)
    else:
        entry = value.to_frame(uri).T.astype(song_db_template)

    # Add entry and avoid duplicates
    song_db = pd.concat([song_db, entry])
    song_db = song_db[~song_db.index.duplicated(keep='last')]
    song_db.to_parquet(song_db_file.format(''))
    return


def pop_song_db(uri: str):
    """ remove entry from song database"""
    sdb = get_song_db()
    item = sdb.loc[uri]
    print(f'Deleted song data base entry "{item.title}" by "{item.album_artist}" ({uri})')
    get_song_db().drop(uri).to_parquet(song_db_file.format(''))


if __name__ == '__main__':
    try:
        then = now()
        sdb = get_song_db()
        duration = now() - then

        n_records = len(sdb)
        to_do = sdb.title.notna()
        n_to_do = to_do.sum()
        n_empty_records = n_records - n_to_do

        backup_exists = os.path.isfile(tmp_path)
        backup_exists = 'exists' if backup_exists else 'does not exist'
        ps = 35

        info = [
            ('number of processed records', n_empty_records),
            ('number of unprocessed records', n_to_do),
            ('loading time', f'{duration:.3f}s'),
            ('location', sdb_path),
            ('backup', backup_exists)
        ]
        print('SONG DATA BASE INFORMATION:',
              *['\n- {}{}'.format(k.ljust(30), str(v).rjust(6)) for k, v in info])
        if n_to_do:
            look_closer = input('>>> Do you want to see a list of items, or check per item? List / Item / [No]')
            if input_is('List', look_closer) or input_is('Item', look_closer):
                for i, (uri, record) in enumerate(sdb[to_do].iterrows()):
                    print(f'{str(i + 1).rjust(3)}/{n_to_do}:', uri)
                    print(record)
                    if input_is('Item', look_closer):
                        do_pop = input('>>> Do you want to permanently delete this item from the pending records? Yes / [No]')
                        if input_is('Yes', do_pop):
                            pop_song_db(uri)
    except FileNotFoundError as e:
        print('Failed to load the song data base')

