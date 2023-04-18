import dotenv
from spotipy.oauth2 import SpotifyClientCredentials
from importlib.machinery import SourceFileLoader
import os
import spotipy
import eyed3
eyed3.log.setLevel("ERROR")


def get_settings_path() -> str:
    settings_file = 'settings.txt'
    try:
        full_settings_file = os.path.join(os.path.dirname(__file__), settings_file)
    except NameError:
        full_settings_file = os.path.join(os.getcwd(), settings_file)
    return full_settings_file


def import_settings():
    settings_path = get_settings_path()
    if not os.path.isfile(settings_path):
        raise FileNotFoundError('Settings file "settings.txt" is missing.')
    settings_module = SourceFileLoader('settings', settings_path)
    return settings_module.load_module()


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
music_dir = os.environ.get("MUSIC_DIR")
daemon_dir = os.path.join(home_dir, '.daemons', 'daemon-{}.tmp')
log_dir = os.path.join(home_dir, '.logs', '{}.json')
song_db_file = os.path.join(home_dir, '{}song_db.pkl')

# Access Spotify API
spotify_api = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())

