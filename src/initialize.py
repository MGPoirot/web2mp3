from urllib.error import HTTPError

import dotenv
from spotipy.oauth2 import SpotifyClientCredentials
import os
import spotipy
import eyed3
import re
import pathlib
import time
from glob import glob as dumb_glob
from typing import List


eyed3.log.setLevel("ERROR")


class Path(type(pathlib.Path())):
    # Subclass from pathlib.Path that adds .format functionality
    def format(self, *args, **kwargs):
        return Path(str(self).format(*args, **kwargs))

    def replace(self, *args, **kwargs):
        return Path(str(self).replace(*args, **kwargs))


def glob(pathname, *args, **kwargs) -> List[Path]:
    # Support Path by str conversion
    return [Path(i) for i in dumb_glob(str(pathname), *args, **kwargs)]


def set_in_dot_env(key: str, value: str, overwrite=True) -> None:
    """
    Add a key value pair to the .env file.
    Avoids duplications of keys by overwriting.
    """
    # Create an environment file if none exists
    if not ENV_PATH.is_file():
        ENV_PATH.parent.mkdir(exist_ok=True)
        with open(ENV_PATH, 'w') as f:
            f.write('# ENVIRONMENT FILE CREATED AUTOMATICALLY BY WEB2MP3\n')

    # Read the data in the environment file
    with open(ENV_PATH, 'r') as f:
        data = f.read()

    # Ensure the key is in capitals
    key = key.upper()

    # Check if there are previous enties for this key
    old_entries = re.findall(f"{key}=.*?\n", data)

    if not any(old_entries) or not overwrite:
        # Append to the environment file
        with open(ENV_PATH, 'a') as f:
            f.write(f'{key}={value}\n')
    else:
        # Replace the old value of the last entry
        old_entry = old_entries[-1]
        data.replace(old_entry, f'{key}={value}\n')
        with open(ENV_PATH, 'w') as file:
            file.write(data)
    return


def sfy_validator(ans: str) -> bool:
    # Validates user input for Spotify client secret
    return all(c.isdigit() or c.islower() for c in ans) and len(ans) == 32


def pth_validator(ans: str) -> bool:
    # Validates user input for music download directory
    return Path(ans).parent.is_dir()


def location_validator(market: str) -> bool:
    """
    Check if a market is a valid Spotify market

    :param market: The market to check
    :type market: str
    :return: True if market is valid, False otherwise
    :rtype: bool
    """
    l = {"AD", "AE", "AG", "AL", "AM", "AO", "AR", "AT", "AU", "AZ", "BA", "BB",
         "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BN", "BO", "BR", "BS", "BT",
         "BW", "BY", "BZ", "CA", "CD", "CG", "CH", "CI", "CL", "CM", "CO", "CR",
         "CV", "CW", "CY", "CZ", "DE", "DJ", "DK", "DM", "DO", "DZ", "EC", "EE",
         "EG", "ES", "ET", "FI", "FJ", "FM", "FR", "GA", "GB", "GD", "GE", "GH",
         "GM", "GN", "GQ", "GR", "GT", "GW", "GY", "HK", "HN", "HR", "HT", "HU",
         "ID", "IE", "IL", "IN", "IQ", "IS", "IT", "JM", "JO", "JP", "KE", "KG",
         "KH", "KI", "KM", "KN", "KR", "KW", "KZ", "LA", "LB", "LC", "LI", "LK",
         "LR", "LS", "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MG", "MH",
         "MK", "ML", "MN", "MO", "MR", "MT", "MU", "MV", "MW", "MX", "MY", "MZ",
         "NA", "NE", "NG", "NI", "NL", "NO", "NP", "NR", "NZ", "OM", "PA", "PE",
         "PG", "PH", "PK", "PL", "PS", "PT", "PW", "PY", "QA", "RO", "RS", "RW",
         "SA", "SB", "SC", "SE", "SG", "SI", "SK", "SL", "SM", "SN", "SR", "ST",
         "SV", "SZ", "TD", "TG", "TH", "TJ", "TL", "TN", "TO", "TR", "TT", "TV",
         "TW", "TZ", "UA", "UG", "US", "UY", "UZ", "VC", "VE", "VN", "VU", "WS",
         "XK", "ZA", "ZM", "ZW"}
    return market in l


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
    music_dir_default = home_dir / "Music"
    location_default = "US"

    qs = {
        'MUSIC_DIR': ('Music download directory', pth_validator, music_dir_default),
        '# Spotify username': ('Spotify username (optional)', lambda x: 1, 'NA'),
        'SPOTIPY_CLIENT_ID': ('Spotify client ID', sfy_validator, None),
        'SPOTIPY_CLIENT_SECRET': ('Spotify client secret', sfy_validator, None),
        'LOCATION': ('Location', location_validator, location_default)
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
            answer = input(f'  {i}. {q_fmt.ljust(24)}\n    {d_fmt}\n')
            answer = default if not answer and default else answer
            if validator(answer):
                set_in_dot_env(key=k, value=answer)
                break
            else:
                print(f'     "{answer}" is not a valid {question}')
    print('Secrets successfully stored.\n'
          'Web2MP3 set up successful.')


# Where are we?
home_dir = Path(__file__).parents[1]

# Check if Web2MP3 has been set up.
ENV_PATH = Path(home_dir, '.config', '.env')
if not dotenv.find_dotenv(ENV_PATH):
    print("No environment file found. Initiating setup wizard.")
    run_setup_wizard()
dotenv.load_dotenv(ENV_PATH)

# Check if setup file is complete, if not, resume setup
env_keys = 'MUSIC_DIR', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET', 'LOCATION'
env_exists = [True if os.environ.get(v) else False for v in env_keys]
if not all(env_exists):
    print("Incomplete environment file found. Resuming setup.")
    run_setup_wizard()
dotenv.load_dotenv(ENV_PATH)

# Define paths from config env
music_dir = Path(os.environ.get('MUSIC_DIR'))
default_location = os.environ.get('LOCATION')

# future, but currently, nothing is broken so no need to fix anything.
daemon_dir = home_dir / '.daemons' / 'daemon-{}.tmp'
log_dir = home_dir / '.logs' / '{}.{}'
index_path = home_dir / 'src' / 'index'

# Ensure the index path exists
index_path.mkdir(exist_ok=True)

# Clean up to last 50 logs on startup
for log_regex in (log_dir.format('*', 'json'), log_dir.format('*', 'txt')):
    fs = glob(log_regex)
    for f in sorted(fs, key=lambda f: os.path.getmtime(f), reverse=True)[50:]:
        f.unlink()


def auto_cookie() -> Path | str:
    cookie_file = ''
    try:
        cookie_file = next(home_dir.glob('**/*cookies.txt'))
        print(f'A cookie file was found: "{cookie_file}"')
    except StopIteration:
        # Warn the user of the limitations of not setting a COOKIE_FILE
        print('Warning: No COOKIE_FILE was found. \n'
              'Without COOKIE_FILE age restricted download will fail.')
    return cookie_file

# Check if a COOKIE_FILE is set
if not os.environ.get('COOKIE_FILE'):
    cookie_file = auto_cookie()
    set_in_dot_env("COOKIE_FILE", cookie_file)
else:
    cookie_file = os.environ.get('COOKIE_FILE')
    if not os.path.isfile(cookie_file):
        print(f'The cookie file specified does not exist: "{cookie_file}"')
        cookie_file = auto_cookie()
        if len(str(cookie_file)) > 0:
            set_in_dot_env("COOKIE_FILE", cookie_file)


# Access Spotify API
spotify_api = spotipy.Spotify(
    client_credentials_manager=SpotifyClientCredentials()
)


def disp_daemons():
    daemons = glob(daemon_dir.format('*'))
    n_daemons = len(daemons)
    print(f'Found {n_daemons} daemons.')
    for daemon in daemons:
        file_mtime = os.path.getmtime(daemon)
        current_time = time.time()
        time_diff = current_time - file_mtime
        days_diff = round(time_diff / (60 * 60 * 24))
        print(str(daemon).ljust(50), f'{days_diff} days old')


def run_clean_up(prompt=True):
    # run utilities
    disp_daemons()
    daemons = glob(daemon_dir.format('*'))
    if any(daemons):
        rm_daemons = input('Delete all daemon files?  yes/[No]')
        if rm_daemons in 'Yesyes':
            for daemon in daemons:
                os.remove(daemon)
            print('Daemons deleted.')
        else:
            print('Daemons untouched.')


if __name__ == '__main__':
    run_clean_up()
