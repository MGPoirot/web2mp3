import pickle
from spotipy.oauth2 import SpotifyClientCredentials
import os
import inspect
from datetime import datetime
import spotipy
import eyed3
import json


data_dir = r'/srv/dev-disk-by-uuid-1806e0be-96d7-481c-afaa-90a97aca9f92/Plex/' if os.name == 'posix' else os.getcwd()
eyed3.log.setLevel("ERROR")
print_space = 24
spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())


class Logger:
    def __init__(self, url: str, owner='get_track', verbose=False):
        if '=' in url:
            url = url.split('=')[1]
            if '&' in url:
                url = url.split('&')[0]
        else:
            url = url.split('/')[-1]  # short notation

        self.key = url
        self.path = os.path.join(os.getcwd(), 'logdir-' + owner, url + '.json')
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
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


def free_folder(directory: str, owner='pi', logger=print):
    """ Clear any access restrictions and set owner """
    os.system(f"sudo chmod 777 -R '{directory}'")
    os.system(f"sudo chown -R {owner}:{owner} '{directory}'")
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