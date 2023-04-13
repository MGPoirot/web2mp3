import dotenv
import pickle
from spotipy.oauth2 import SpotifyClientCredentials
import os
import inspect
from datetime import datetime
import spotipy
import eyed3
import json
import sys
import importlib.machinery
eyed3.log.setLevel("ERROR")


def hms2s(hhmmss: str) -> int:
    components = hhmmss.split(':')
    components.reverse()
    return sum([int(value) * multiplier for value, multiplier in zip(components, (1, 60, 3600))])


def get_url_domain(track_url: str) -> str:
    patterns = {'open.spotify.com': 'spotify',
                'youtube.com':      'youtube',
                'soundcloud.com':   'soundcloud',
                'youtu.be':         'youtube'}
    for pattern, domain in patterns.items():
        if pattern in track_url:
            return domain
    raise KeyError(f'No pattern found in "{track_url}".\nKnown patterns: {"; ".join(patterns)}')


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


if not dotenv.find_dotenv():
    with open('env', 'w') as fp:
        pass


def get_settings_path():
    settings_file = 'settings.txt'
    try:
        full_settings_file = os.path.join(os.path.dirname(__file__), settings_file)
    except NameError:
        full_settings_file = os.path.join(os.getcwd(), settings_file)
    return full_settings_file


def import_settings():
    return importlib.machinery.SourceFileLoader('settings', get_settings_path()).load_module()


def run_setup_wizard():
    web2mp3home = os.getcwd()
    music_dir_default = os.path.join(web2mp3home, "Music")

    sp_validator = lambda ans: all(c.isdigit() or c.islower() for c in ans) and len(ans) == 32
    pth_validator = lambda pth: os.path.isdir(os.path.dirname(pth))

    questions = {'HOME_DIR':                ('Web2MP3 home directory',   pth_validator, web2mp3home),
                 'MUSIC_DIR':               ('Music download directory', pth_validator, music_dir_default),
                 'SPOTIFY_CLIENT_ID':       ('Spotify client ID',        sp_validator,  None),
                 'SPOTIFY_CLIENT_SECRET':   ('Spotify client secret',    sp_validator,  None)}

    print(f'                      --- Welcome to Web2MP3 ---                   \n'
          f'The absence of a .env file indicates that Web2MP3 has not been set up.\n'
          f'Please provide 4 secrets that will be locally stored in a ".env" file:')
    for i, (key, (question, validator, default)) in enumerate(questions.items(), 1):
        while True:
            q_fmt = f'   {i}. What is your {question}?'
            d_fmt = f'[{default}]' if default else ''
            answer = input(f'{q_fmt.ljust(settings.print_space)} {d_fmt}\n')
            answer = default if not answer and default else answer
            if validator(answer):
                with open('.env', 'a') as f:
                    f.write(f'{key} = {answer}\n')
                break
            else:
                print(f'"{answer}" is not a valid {question}')
    print('Secrets successfully stored. You are good to go.')


settings = import_settings()
if not dotenv.find_dotenv():
    run_setup_wizard()
dotenv.load_dotenv()
home_dir = os.environ.get("HOME_DIR")
daemon_dir   = os.path.join(home_dir, '.daemons', 'daemon-{}.tmp')
log_dir      = os.path.join(home_dir, '.logs', '{}.json')
song_db_file = os.path.join(home_dir, 'song_db.pkl')
spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())

