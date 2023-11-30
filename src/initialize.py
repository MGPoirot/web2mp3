import dotenv
from spotipy.oauth2 import SpotifyClientCredentials
import os
import spotipy
import eyed3
import re
from pathlib import Path as Path
from glob import glob
import time

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


def market_validator(market: str) -> bool:
    """
    Check if a market is a valid Spotify market

    :param market: The market to check
    :type market: str
    :return: True if market is valid, False otherwise
    :rtype: bool
    """
    l = ["AD", "AE", "AG", "AL", "AM", "AO", "AR", "AT", "AU", "AZ", "BA", "BB",
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
         "XK", "ZA", "ZM", "ZW"]
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
    market_default = "US"

    qs = {
        'MUSIC_DIR': ('Music download directory',
                      pth_validator, music_dir_default),
        '# Spotify username': ('Spotify username (optional)',
                               lambda x: True, 'None'),
        'SPOTIPY_CLIENT_ID': ('Spotify client ID',
                              sfy_validator, None),
        'SPOTIPY_CLIENT_SECRET': ('Spotify client secret',
                                  sfy_validator, None),
        'SPOTIFY_MARKET': ('Spotify market',
                           market_validator, market_default)
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
            answer = input(f'  {i}. {q_fmt.ljust(24)}\n'
                           f'    {d_fmt}\n')
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
env_keys = 'MUSIC_DIR', 'SPOTIPY_CLIENT_ID', \
    'SPOTIPY_CLIENT_SECRET', 'SPOTIFY_MARKET'
env_vals = [os.environ.get(v) for v in env_keys]
if None in env_vals:
    print("Incomplete environment file found. Resuming setup.")
    run_setup_wizard()
dotenv.load_dotenv(ENV_PATH)

# Define paths from config env
music_dir = Path(os.environ.get('MUSIC_DIR'))
default_market = os.environ.get('SPOTIFY_MARKET')

# Maybe I will replace the use of string with Path objects here as well in the
# future, but currently, nothing is broken so no need to fix anything.
daemon_dir = str(home_dir / '.daemons' / 'daemon-{}.tmp')
log_dir = str(home_dir / '.logs' / '{}.json')
song_db_file = str(home_dir / '{}song_db.pqt')

     
# Check if a COOKIE_FILE is set
if not os.environ.get('COOKIE_FILE'):
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


def disp_daemons():
    daemons = glob(daemon_dir.format('*'))
    n_daemons = len(daemons)
    print(f'Found {n_daemons} daemons.')
    for daemon in daemons:
        file_mtime = os.path.getmtime(daemon)
        current_time = time.time()
        time_diff = current_time - file_mtime
        days_diff = round(time_diff / (60 * 60 * 24))
        print(daemon.ljust(60), f'{days_diff} days old')


if __name__ == '__main__':
    # run utilities

    # Check number of existing log files
    log_files_json = glob(log_dir.format('*'))
    log_files_txt = glob(log_dir.format('*').replace('.json', '.txt'))
    log_files = log_files_json + log_files_txt
    n_log_files = len(log_files)
    if n_log_files > 100:
        rm_logs = input(f'Initialization found many {n_log_files} log files. Remove up to last 100?  yes/[No]  ')
        if rm_logs in 'Yesyes':
            # rm log files
            log_files = sorted(log_files, key=lambda x: os.path.getmtime(x))
            for log_file in log_files[:-100]:
                os.remove(log_file)
            print(n_log_files - 100, 'log files deleted.')
            pass
    else:
        print(f'Found {n_log_files} log files.')
    disp_daemons()
    daemons = glob(daemon_dir.format('*'))
    if any(daemons):
        rm_daemons = input('Delete all daemon files?  yes/[No]')
        if rm_daemons in 'Yesyes':
            for daemon in daemons:
                os.remove(daemon)
