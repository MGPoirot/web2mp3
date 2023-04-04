from utils import pickle_in, pickle_out
import os


song_db_file = os.path.join(os.getcwd(), '../song_db.pkl')


def get_song_db() -> dict:
    """
    Load the Song Data Base (song_db) file, or
    create one if it does not exist.
    The song_db is used to store song properties and URLs of past processes.
    """
    if not os.path.isfile(song_db_file):
        pickle_out({}, song_db_file)
    return pickle_in(song_db_file)


def set_song_db(youtube_url: str, value=None):
    """
    Set a value to a key (=YouTube URL) in the song database
    """
    song_db = get_song_db()
    song_db[youtube_url] = value
    pickle_out(song_db, song_db_file)
    return


def pop_song_db(youtube_url: str):
    """ remove entry from song database"""
    song_db = get_song_db()
    del song_db[youtube_url]
    pickle_out(song_db, song_db_file)
