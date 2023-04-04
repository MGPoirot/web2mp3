from dotenv import load_dotenv
load_dotenv()
import pickle
from spotipy.oauth2 import SpotifyClientCredentials
from contextlib import contextmanager
import os
import inspect
from datetime import datetime
import spotipy
import eyed3
import json
import sys


def get_url_domain(track_url: str) -> str:
    # return 'soundcloud'
    # return 'spotify'
    return 'youtube'


def shorten_url(url: str) -> str:
    if '=' in url:
        url = url.split('=')[1] if '=' in url else url
    else:
        url = url.split('/')[-1]
    return url.split('&')[0]


class Logger:
    def __init__(self, full_path=None, verbose=False):
        """
        Except from verbose, all arguments are used to contruct a path. Two options:
        1. full_path
        2. os.getcwd()/logdir-[OWNER]/URL.json
        """

        self.path = full_path
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except OSError:
            raise OSError(f'Not a valid path: "{self.path}"')
            sys.exit()
        self.verbose = verbose  # Always print if true

        if not os.path.isfile(self.path):
            json_out({}, self.path)
        self(datetime.now().strftime("%Y-%m-%d %H:%M"))

    def __call__(self, *text, verbose=False):
        # Find out who called the logger
        curframe = inspect.currentframe()
        calframe = inspect.getouterframes(curframe, 2)
        caller   = calframe[1][3]

        # See if this caller has recently logged anything
        log_dict = json_in(self.path)
        existing_caller_ids = [k for k in log_dict if caller in k]
        if not any(existing_caller_ids):
            caller_id = f'{str(len(log_dict)).zfill(3)}-{caller}'
            log_dict[caller_id] = []
        else:
            caller_id = existing_caller_ids[-1]

        # Log text
        log_dict[caller_id].append(' '.join(text))
        json_out(log_dict, self.path)
        if verbose or self.verbose:
            print(*text)

    def close(self):
        self(datetime.now().strftime("%Y-%m-%d %H:%M"))

    def rm(self):
        if os.path.isfile(self.path):
            os.remove(self.path)


def free_folder(directory: str, owner='pi', logger=print):
    # As long as you do not run the command as sudo, you should not end up with ownership issues
    """ Clear any access restrictions and set owner """
    os.system(f"sudo chmod 777 -R '{directory}'")
    os.system(f"sudo chown -R {owner}:{owner} '{directory}'")
    #os.chmod(file, 0o0777)
    #os.chown(file, pwd.getpwnam('plex').pw_uid, )
    logger(f'Rights set to rwxrwsrwx and owner to {owner} for "{directory}"')


def input_is(control: str, input_str: str) -> bool:
    """
    check if user input matches either the first letter as capital or full string
    :param control: the capitalized string to control against (e.g. Return)
    :param input_str: the input provided by the user
    :return: bool if there is match yes or no
    """
    return input_str.lower() == control.lower() or input_str.upper() == control[0]


def json_in(source: str):
    with open(source, 'r') as file:
        return json.load(file)


def json_out(obj: dict, target: str):
    with open(target, 'w') as file:
        json.dump(obj, file, indent=4, sort_keys=True)


def pickle_in(source: str) -> dict:
    with open(source, 'rb') as file:
        return pickle.load(file)


def pickle_out(obj: dict, target: str):
    with open(target, 'wb') as file:
        pickle.dump(obj, file)


def flatten(lst: list):
    """
    Flatten a nested that contains lists (nested)
    :param lst: Nested list
    :return: Unested list
    """
    return [item for sublist in lst for item in sublist]


def rm_char(text: str) -> str:
    """
    Remove illegal characters from string. This is useful for creating legal paths.
    :param text: input string potentially containing illegal characters
    :return: output string cleaned of illegal characters
    """
    for char in '.#%&{}\<>*?/$!":@|`|=\'':
        text = text.replace(char, '')
    return text


data_dir = r'/srv/dev-disk-by-uuid-1806e0be-96d7-481c-afaa-90a97aca9f92/Plex/' if os.name == 'posix' else r'C:\Users\mpoir\Music'
data_dir = os.path.join(data_dir)
daemon_dir = os.path.join(os.getcwd(), '.daemons', 'daemon-{}.tmp')
log_dir = os.path.join(os.getcwd(), '.logs', '{}.json')
song_db_file = os.path.join(os.getcwd(), 'song_db.pkl')
eyed3.log.setLevel("ERROR")
print_space = 24
spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())
max_daemons = 2