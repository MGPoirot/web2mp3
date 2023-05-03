import dotenv
from spotipy.oauth2 import SpotifyClientCredentials
import os
import spotipy
import eyed3
import re
from pathlib import Path as Path
eyed3.log.setLevel("ERROR")


class FmtPath(os.PathLike):
    """
    Appends format functionality to pathlib.Path defined objects.
    NB: returns regular Path objects.
    """
    def __init__(self, *args, **kwargs):
        self._path = Path(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._path, name)

    def format(self, *args, **kwargs):
        return Path(str(self._path).format(*args, **kwargs))

    def __fspath__(self):
        return str(self._path)


def set_in_dot_env(key: str, value: str, overwrite=True):
    key = key.upper()
    if not ENV_PATH.is_file():
        # Write first entry
        ENV_PATH.parent.mkdir(exist_ok=True)
        with open(ENV_PATH, 'w') as f:
            f.write(f'{key}={value}\n')
        return
    else:
        with open(ENV_PATH, 'r') as f:
            data = f.read()

    old_entries = re.findall(f"{key}=.*?\n", data)
    if not any(old_entries) or not overwrite:
        # Append new entry
        with open(ENV_PATH, 'a') as f:
            f.write(f'{key}={value}\n')
        return
    elif len(old_entries) > 1:
        print(f'ValueWarning: Key "{key}" found {len(old_entries)} times. '
              f'Replace is ambiguous. Replacing last entry.')
    old_entry = old_entries[-1]
    data.replace(old_entry, f'{key}={value}\n')
    with open('file.txt', 'w') as file:
        file.write(data)


def sfy_validator(ans: str) -> bool:
    return all(c.isdigit() or c.islower() for c in ans) and len(ans) == 32


def pth_validator(ans: str) -> bool:
    return Path(ans).parent.is_dir()


def run_setup_wizard():
    """
    Runs the setup wizard for Web2MP3 and stores user input in a ".env" file.

    Prompts user for input regarding:
     - the Web2MP3 home directory
     - music download directory
     - Spotify username (optional)
     - Spotify client ID
     - Spotify client
    Validates user input and writes it to a ".env" file.

    :return: None
    """
    print_space = 24

    web2mp3home = Path.cwd()
    music_dir_default = web2mp3home / "Music"

    qs = {
        'HOME_DIR':                ('Web2MP3 home directory',
                                    pth_validator,  web2mp3home),
        'MUSIC_DIR':               ('Music download directory',
                                    pth_validator,  music_dir_default),
        '# Spotify username':      ('Spotify username (optional)',
                                    lambda x: True, 'None'),
        'SPOTIPY_CLIENT_ID':       ('Spotify client ID',
                                    sfy_validator,  None),
        'SPOTIPY_CLIENT_SECRET':   ('Spotify client secret',
                                    sfy_validator,  None),
    }
    print("                         , - ~ ~ ~ - ,                           \n"
          "                     , '   WEB 2 MP3   ' ,                       \n"
          "                   ,                       ,                     \n"
          "                  ,         |~~~~~~~|       ,                    \n"
          "                 ,          |~~~~~~~|        ,                   \n"
          "                 ,          |       |        ,                   \n"
          "                 ,      /~~\|   /~~\|        ,                   \n"
          "                  ,     \__/    \__/        ,                    \n"
          "                   ,                       ,                     \n"
          "                     ,Music Download CLI, '                      \n"
          "                       ' - , _ _ _ ,  '                          \n")
    print('Welcome to Web2MP3. No setup file (".env") was found. The setup  \n'
          'wizard will as a few questions to set up Web2MP3. Answers are    \n'
          'secret and stored in the ".env" file. If available, a proposed   \n'
          'default is suggested in brackets:                                \n')
    for i, (k, (question, validator, default)) in enumerate(qs.items(), 1):
        while True:
            q_fmt = f'What is your {question}?'
            default = default if not os.environ.get(k) else os.environ.get(k)
            d_fmt = f'[{default}]' if default else ''
            answer = input(f'  {i}. {q_fmt.ljust(print_space)}\n'
                           f'    {d_fmt}\n')
            answer = default if not answer and default else answer
            if validator(answer):
                set_in_dot_env(key=k, value=answer)
                break
            else:
                print(f'     "{answer}" is not a valid {question}')
    print('Secrets successfully stored.\n'
          'Web2MP3 set up successful.')


# Check if Web2MP3 has been set up.
ENV_PATH = Path('.config', '.env')
if not dotenv.find_dotenv(ENV_PATH):
    print("No environment file found. Initiating setup wizard.")
    run_setup_wizard()
dotenv.load_dotenv(ENV_PATH)

# Check if setup file is complete, if not, resume setup
env_keys = 'HOME_DIR', 'MUSIC_DIR', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET'
env_vals = [os.environ.get(v) for v in env_keys]
if None in env_vals:
    print("Incomplete environment file found. Resuming setup.")
    run_setup_wizard()
dotenv.load_dotenv(ENV_PATH)

# Define paths from config env
home_dir = Path(os.environ.get('HOME_DIR'))
music_dir = Path(os.environ.get('MUSIC_DIR'))
daemon_dir = str(home_dir / '.daemons' / 'daemon-{}.tmp')
log_dir = str(home_dir / '.logs' / '{}.json')
song_db_file = str(home_dir / '{}song_db.pqt')

# Check if a COOKIE_FILE is set
if os.environ.get('COOKIE_FILE') is None:
    try:
        cookie_file = next(home_dir.glob('**/*_cookies.txt'))
    except StopIteration:
        # Warn the user of the limitations of not setting a COOKIE_FILE
        print('Warning: No COOKIE_FILE was found. \n'
              'Without COOKIE_FILE age restricted download will fail.')
        cookie_file = ''
    set_in_dot_env("COOKIE_FILE", cookie_file)
else:
    cookie_file = os.environ.get('COOKIE_FILE')

# Access Spotify API
spotify_api = spotipy.Spotify(
    client_credentials_manager=SpotifyClientCredentials()
)
