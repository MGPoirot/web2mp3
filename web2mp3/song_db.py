from setup import song_db_file
import pandas as pd
import os
from time import time


def get_song_db() -> dict:
    """
    Load the Song Data Base (song_db) file, or
    create one if it does not exist.
    The song_db is used to store song properties and URLs of past processes.
    """
    # Load the song data base is it exists
    sdb_path = song_db_file.format('')
    if not os.path.isfile(sdb_path):
        pd.DataFrame().to_pickle(sdb_path)
    sdb = pd.read_pickle(sdb_path)

    # Evert 4 minutes we also store a temporary file
    tmp_path = song_db_file.format('.')
    if not os.path.isfile(tmp_path):
        sdb.to_pickle(tmp_path)
    elif time() - os.stat(sdb_path).st_mtime > 240:
        sdb.to_pickle(tmp_path)

    return sdb


def set_song_db(uri: str, value=None):
    """
    Set a value to a key (=short URL) in the song database
    """
    song_db = get_song_db()
    song_db.loc[uri] = pd.Series(value, dtype='O')
    song_db.to_pickle(song_db_file.format(''))
    return


def pop_song_db(uri: str):
    """ remove entry from song database"""
    get_song_db().drop(uri).to_pickle(song_db_file.format(''))
