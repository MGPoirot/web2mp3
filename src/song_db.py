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
    'title': PdStr(),
    'album': PdStr(),
    'album_artist': PdStr(),
    'duration': PdFlt(),
    'bpm': PdInt(),
    'artist': PdStr(),
    'internet_radio_url': PdStr(),
    'cover': PdStr(),
    'disc_num': object,
    'genre': PdStr(),
    'release_date': PdStr(),
    'recording_date': PdStr(),
    'tagging_date': PdStr(),
    'track_num': object,
    'kwarg_print_space': PdInt(),
    'kwarg_max_daemons': PdInt(),
    'kwarg_verbose': PdBool(),
    'kwarg_verbose_single': PdBool(),
    'kwarg_do_overwrite': PdBool(),
    'kwarg_quality': PdInt(),
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
        sdb.to_pickle(sdb_path)
    try:
        # Test if the file can be loaded
        sdb = pd.read_pickle(sdb_path)
    except UnicodeDecodeError:
        print('The song data base was corrupted. Loading from backup.')
        shutil.copy(tmp_path, sdb_path)
        sdb = pd.read_pickle(sdb_path)

    # Evert minute we also store a backup
    if not os.path.isfile(tmp_path):
        sdb.to_pickle(tmp_path)
    elif time() - os.stat(sdb_path).st_mtime > 60:
        sdb.to_pickle(tmp_path)
    return sdb


def set_song_db(uri: str, value=None):
    """ Set a value to a key (=short URL) in the song database """
    song_db = get_song_db()
    dtype = {'dtype': 'O'} if value is None else {}
    song_db.loc[uri] = pd.Series(value, **dtype)
    song_db.to_pickle(song_db_file.format(''))
    return


def pop_song_db(uri: str):
    """ remove entry from song database"""
    get_song_db().drop(uri).to_pickle(song_db_file.format(''))
