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
    """
    Converts a string representing time in the format "hh:mm:ss" to seconds.

    Args:
        :param hhmmss: The time in the format "hh:mm:ss", "mm:ss" or "ss".
        :type hhmmss: str

    Returns:
        :return: The time in seconds.
        :rtype: int
    """
    components = hhmmss.split(':')
    components.reverse()
    return sum([int(value) * multiplier for value, multiplier in zip(components, (1, 60, 3600))])


def get_url_domain(track_url: str) -> str:
    """
    The function get_url_domain extracts the domain name from a given URL. If a
     known domain is found in the URL, it returns the corresponding domain name
     as a string. Otherwise, it raises a KeyError with a list of known domain
     patterns.

    Args:
        :param track_url: The URL string to extract the domain from.
        :type track_url: str

    Returns:
        :return: The extracted domain name string.
        :rtype: str

    Raises:
        :raise KeyError: If the URL does not contain any known domain patterns.

    Example:
        > get_url_domain('http://open.spotify.com/track/0PCM1aBGD8kGJmBizoW2iM')
        'spotify'

        > get_url_domain('https://www.youtube.com/watch?v=NgE5mEQiizQ')
        'youtube'

        > get_url_domain('https://on.soundcloud.com/H4C3V')
        'soundcloud'
    """
    patterns = {'open.spotify.com': 'spotify',
                'youtube.com':      'youtube',
                'soundcloud.com':   'soundcloud',
                'youtu.be':         'youtube'}
    for pattern, domain in patterns.items():
        if pattern in track_url:
            return domain
    raise KeyError(f'No pattern found in "{track_url}".'
                   f'\nKnown patterns: {"; ".join(patterns)}')


def shorten_url(url: str) -> str:
    """
    Shortens a URL by extracting the relevant part from it.

    Args:
        :param url: The URL to be shortened.
        :type url: str

    Returns:
        :return: The shortened URL.
        :rtype: str

    Example:
        > shorten_url(r'https://www.youtube.com/watch?v=z6aONWHhTCU')
        z6aONWHhTCU
    """
    if '=' in url:
        url = url.split('=')[1] if '=' in url else url
    else:
        url = url.split('/')[-1]
    return url.split('&')[0]


class Logger:
    """
    A class for logging information and errors to a file.

    Attributes:
        :attr path: The full path to the log file.
        :type path: str
        :attr verbose: Whether to print log messages to console as well.
        :type verbose: bool
    """
    def __init__(self, full_path=None, verbose=False):
        """
        Initializes the logger.

        Args:
            :param full_path: The full path to the log file.
            :type full_path: str or NoneType
            :param verbose: Whether to print log messages to console as well.
            :type verbose: bool

        Raises:
            :raises OSError: If `full_path` is not a valid path.
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
        """
        Logs the given `text` with the name of the calling function.

        Args:
            :param text: The text to log.
            :param verbose: Whether to print log messages to console as well.

        Returns:
            :return: None
        """
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
        """
        Writes a closing timestamp to the log file.

        Returns:
            :return: None
        """
        self(datetime.now().strftime("%Y-%m-%d %H:%M"))

    def rm(self):
        """
        Removes the log file from the filesystem.

        Returns:
            :return: None
        """
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
    Check if the user input matches either the first letter capitalized or the
     full string.

    Args:
        :param control: The capitalized string to compare against.
        :type control: str
        :param input_str: The input provided by the user.
        :type input_str: str

    Returns:
        :return: True if there is a match, False otherwise.
        :rtype: bool

    Example:
        > input_is('Return', 'R')
        True
        > input_is('Return', 'r')
        True
        > input_is('Return', 'Return')
        True
        > input_is('Return', 'return')
        True
        > input_is('Return', 'Ret')
        False
    """
    return input_str.lower() == control.lower() or input_str.upper() == control[0]


def json_in(source: str):
    """
    Read data from a JSON file and return a dictionary object

    :param source: The path to the JSON file
    :type source: str
    :return: A dictionary object representing the JSON data
    :rtype: dict
    """
    with open(source, 'r') as file:
        return json.load(file)


def json_out(obj: dict, target: str):
    """
    Write dictionary object to a JSON file

    :param obj: The dictionary object to be written
    :type obj: dict
    :param target: The path to the output JSON file
    :type target: str
    """
    with open(target, 'w') as file:
        json.dump(obj, file, indent=4, sort_keys=True)


def pickle_in(source: str) -> dict:
    """
    Read data from a pickle file and return a dictionary object

    :param source: The path to the pickle file
    :type source: str
    :return: A dictionary object representing the pickle data
    :rtype: dict
    """
    with open(source, 'rb') as file:
        return pickle.load(file)


def pickle_out(obj: dict, target: str):
    """
    Write dictionary object to a pickle file

    :param obj: The dictionary object to be written
    :type obj: dict
    :param target: The path to the output pickle file
    :type target: str
    """
    with open(target, 'wb') as file:
        pickle.dump(obj, file)


def flatten(lst: list) -> list:
    """
    Flattens a nested list that contains sub-lists.

    Args:
        :param lst: A nested list.
        :type lst: list

    Returns:
        :return: An unnested list.
        :rtype: list

    Example:
        > nested_list = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        > flatten(nested_list)
        [1, 2, 3, 4, 5, 6, 7, 8, 9]
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
    web2mp3home = os.getcwd()
    music_dir_default = os.path.join(web2mp3home, "Music")

    sfy_validator = lambda ans: all(c.isdigit() or c.islower() for c in ans) and len(ans) == 32
    pth_validator = lambda pth: os.path.isdir(os.path.dirname(pth.encode('unicode_escape')))

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
            d_fmt = f'[{repr(default)}]' if default else ''
            answer = input(f'  {i}. {q_fmt.ljust(settings.print_space)}\n'
                           f'    {d_fmt}\n')
            answer = default if not answer and default else answer
            if validator(answer):
                with open('.env', 'a') as f:
                    f.write(f'{k}={repr(answer)}\n')
                break
            else:
                print(f'     "{answer}" is not a valid {question}')
    print('Secrets successfully stored.\n'
          'Web2MP3 set up successful.')

# Import public settings
settings = import_settings()

# Check if Web2MP3 has been set up.
if not dotenv.find_dotenv():
    print("No environment file found. Initiating setup wizard.")
    run_setup_wizard()
dotenv.load_dotenv()

# Check if setup file is complete, if not, resume setup
env_keys = 'HOME_DIR', 'MUSIC_DIR', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET'
env_vals = [os.environ.get(v) for v in env_keys]
if None in env_vals:
    print("Incomplete environment file found. Resuming setup.")
    run_setup_wizard()
dotenv.load_dotenv()

# Define other paths
home_dir = os.environ.get("HOME_DIR")
daemon_dir = os.path.join(home_dir, '.daemons', 'daemon-{}.tmp')
log_dir = os.path.join(home_dir, '.logs', '{}.json')
song_db_file = os.path.join(home_dir, 'song_db.pkl')

# Access Spotify API
spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())



