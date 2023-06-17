from initialize import song_db_file
import pandas as pd
import os
from time import time
import shutil
from pandas import Int64Dtype as PdInt
from pandas import BooleanDtype as PdBool
from pandas import StringDtype as PdStr
from pandas import Float32Dtype as PdFlt


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


def get_song_db() -> pd.DataFrame:
    """
    Load the Song Data Base (song_db) file, or
    create one if it does not exist.
    The song_db is used to store song properties for them to be processed and
    URLs of past processes in order to avoid processing them twice.
    """
    # Load the song database is it exists
    sdb_path = song_db_file.format('')
    tmp_path = song_db_file.format('.')

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
    elif time() - os.stat(sdb_path).st_mtime > 60:
        sdb.to_parquet(tmp_path)

    if not sdb['_kwarg_print_space'].dtype == pd.Int64Dtype():
        print('a thief! ruined the dtype')
        breakpoint()

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
    get_song_db().drop(uri).to_parquet(song_db_file.format(''))
