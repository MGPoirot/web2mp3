from urllib.error import HTTPError

from spotipy.oauth2 import SpotifyOAuth
import os
import shutil
import spotipy
import eyed3
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


def _fallback(key: str, default: str) -> str:
    """Read an env var, falling back to a printed-and-used default if unset."""
    val = os.environ.get(key)
    if val:
        return val
    print(f'[web2mp3] "{key}" not set, falling back to default: {default!r}')
    return default


def _require(key: str, hint: str) -> str:
    """Read a required env var, failing fast with actionable guidance if unset."""
    val = os.environ.get(key)
    if not val:
        print(f'[web2mp3] ERROR: required environment variable "{key}" is not set.')
        print(f'          {hint}')
        raise SystemExit(1)
    return val


def _auto_deno_bin() -> str:
    # Prefer explicit env
    p = os.environ.get("DENO_BIN")
    if p and os.path.isfile(p) and os.access(p, os.X_OK):
        return p

    # PATH
    p = shutil.which("deno")
    if p and os.path.isfile(p) and os.access(p, os.X_OK):
        return p

    # Common root install
    p = "/root/.deno/bin/deno"
    if os.path.isfile(p) and os.access(p, os.X_OK):
        return p

    return ""


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


# Where are we?
home_dir = Path(__file__).parents[1]

music_dir = Path(_fallback('MUSIC_DIR', '/music'))
default_location = _fallback('LOCATION', 'US')
if not location_validator(default_location):
    print(f'[web2mp3] Warning: "{default_location}" is not a recognized Spotify '
          f'market code; Spotify API calls using it may fail.')

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


COOKIE_HELP_TEXT = (
    'No cookie file found. Age-restricted YouTube downloads need one. To get one:\n'
    '  1. Install the browser extension "Get cookies.txt LOCALLY"\n'
    '  2. Go to youtube.com while logged in\n'
    '  3. Open the extension and export your cookies\n'
    '  4. Save the file into ./.config/ (any name ending in "_cookies.txt")\n'
    'The exported file must contain a "__Secure-1PSID" cookie.'
)


def auto_cookie() -> Path | str:
    cookie_file = ''
    try:
        cookie_file = next(home_dir.glob('**/*cookies.txt'))
        print(f'A cookie file was found: "{cookie_file}"')
    except StopIteration:
        print(COOKIE_HELP_TEXT)
    return cookie_file


# Resolve COOKIE_FILE
if not os.environ.get('COOKIE_FILE'):
    cookie_file = auto_cookie()
else:
    cookie_file = os.environ.get('COOKIE_FILE')
    if not os.path.isfile(cookie_file):
        print(f'The cookie file specified does not exist: "{cookie_file}"')
        cookie_file = auto_cookie()

# Resolve DENO_BIN (optional but recommended for reliable yt-dlp EJS)
deno_bin = _auto_deno_bin()
if not deno_bin:
    print(
        "Warning: deno not found. YouTube signature solving may fail (yt-dlp EJS)."
    )

ytdlp_remote_components = os.environ.get("YTDLP_REMOTE_COMPONENTS", "ejs:github")


# Access Spotify API
#
# Spotipy (requests) has no timeout by default, which can look like the CLI is
# "hanging" indefinitely on a single Web API request.
#
# We set a finite request timeout and disable Spotipy's own retry/backoff so that
# our explicit Retry-After-aware backoff logic (utils.call_with_backoff) is what
# governs waiting/retrying.

_spotify_client = None


def get_spotify_client() -> spotipy.Spotify:
    """
    Lazily constructs (and memoizes) the Spotify client. Deferred until
    actually needed (rather than built at import time) so that commands
    that don't talk to Spotify — e.g. the `cookie`/`inspect` CLI subcommands
    — work even before SPOTIPY_CLIENT_ID/SECRET are configured.
    """
    global _spotify_client
    if _spotify_client is None:
        client_id = _require(
            'SPOTIPY_CLIENT_ID',
            'Get one from https://developer.spotify.com/dashboard and set it in .env',
        )
        client_secret = _require(
            'SPOTIPY_CLIENT_SECRET',
            'Get one from https://developer.spotify.com/dashboard and set it in .env',
        )
        _spotify_client = spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                scope="playlist-read-private playlist-read-collaborative",
                redirect_uri=os.environ.get("SPOTIPY_REDIRECT_URI", "https://maartenpoirot.com/contact"),
                cache_path=str(home_dir / '.config' / '.spotify_cache'),
                open_browser=False,
            ),
            requests_timeout=float(os.environ.get("SPOTIFY_REQUEST_TIMEOUT", "15")),
            retries=0,
            status_retries=0,
            backoff_factor=0,
        )
    return _spotify_client


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
