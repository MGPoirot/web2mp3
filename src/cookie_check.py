"""
Non-interactive cookie-file check for the `cookie` CLI subcommand and the GUI.

Reports whether a cookie file is configured/auto-detected and whether it
looks like a valid YouTube cookies export, or prints setup guidance if not.

Usage: python src/cookie_check.py
"""
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from initialize import COOKIE_HELP_TEXT, home_dir  # noqa: E402

# Cookies YouTube only sets for a signed-in session. A file can be full of
# VISITOR_INFO1_LIVE/PREF/SOCS entries and still be signed out, so presence of
# these specifically is what separates "exported while logged in" from "not".
LOGIN_COOKIES = ('__Secure-1PSID', '__Secure-3PSID')

MAX_COOKIE_BYTES = 1_000_000


@dataclass
class CookieStatus:
    ok: bool
    message: str
    path: str | None = None


def cookie_names(content: str) -> set[str]:
    """Cookie names from a Netscape cookie file.

    Matched exactly on the name field: a substring test would accept
    "__Secure-1PSIDTS" (a rotation timestamp, present even when signed out)
    as if it were "__Secure-1PSID".
    """
    names = set()
    for line in content.splitlines():
        line = line.removeprefix('#HttpOnly_')
        if not line.strip() or line.startswith('#'):
            continue
        fields = line.split('\t')
        if len(fields) >= 7:
            names.add(fields[5])
    return names


def first_cookie_file() -> Path | None:
    """First `*cookies.txt` under the app root, same order as startup auto-detect."""
    try:
        return Path(next(home_dir.glob('**/*cookies.txt')))
    except StopIteration:
        return None


def resolve_cookie_path() -> Path | None:
    """Path the app will load right now.

    Re-scanned on every call. `initialize.cookie_file` is fixed at import, so
    a long-lived process (the GUI) must not trust it after an upload.
    """
    env = os.environ.get('COOKIE_FILE')
    if env and os.path.isfile(env):
        return Path(env)
    return first_cookie_file()


def destination_path() -> Path:
    """Where an accepted upload is written so the next download loads it.

    `COOKIE_FILE` wins even when that path does not exist yet, matching the
    env var over a stray glob match. Otherwise overwrite the file auto-detect
    would pick. Otherwise the default bind-mounted location.
    """
    env = os.environ.get('COOKIE_FILE')
    if env:
        return Path(env)
    found = first_cookie_file()
    if found:
        return found
    return Path(home_dir) / '.config' / 'cookies.txt'


def assess_content(content: str, path: str | None = None) -> CookieStatus:
    """Validate Netscape cookie text. Does not touch the filesystem."""
    if not content.strip():
        where = f': "{path}"' if path else ''
        return CookieStatus(
            False,
            f'Cookie file is empty{where}\n{COOKIE_HELP_TEXT}',
            path,
        )

    names = cookie_names(content)
    if not names:
        return CookieStatus(
            False,
            'This does not look like a Netscape cookies.txt export '
            '(no tab-separated cookie lines).\n' + COOKIE_HELP_TEXT,
            path,
        )

    missing = [c for c in LOGIN_COOKIES if c not in names]
    if missing:
        loc = f'found at "{path}"' if path else 'uploaded'
        lines = [
            f'Cookie file {loc} but it is not logged in '
            f'(missing {", ".join(missing)}) — age-restricted downloads '
            f'will fail with "Sign in to confirm your age".',
            f'It only holds {len(names)} non-login cookies, which is what '
            f'a signed-out or expired session looks like.',
            COOKIE_HELP_TEXT,
        ]
        return CookieStatus(False, '\n'.join(lines), path)

    where = f': "{path}"' if path else ''
    return CookieStatus(True, f'Cookie file looks valid{where}', path)


def assess_file(path: Path) -> CookieStatus:
    if not path.is_file():
        return CookieStatus(
            False,
            f'Configured cookie file does not exist: "{path}"\n{COOKIE_HELP_TEXT}',
            str(path),
        )
    content = path.read_text(errors='replace')
    return assess_content(content, path=str(path))


def assess_installed() -> CookieStatus:
    """Re-read whatever cookie file startup would use."""
    env = os.environ.get('COOKIE_FILE')
    if env and os.path.isfile(env):
        return assess_file(Path(env))
    found = first_cookie_file()
    if found:
        return assess_file(found)
    if env:
        return CookieStatus(
            False,
            f'Configured cookie file does not exist: "{env}"\n{COOKIE_HELP_TEXT}',
            env,
        )
    return CookieStatus(False, COOKIE_HELP_TEXT, None)


def save_cookie_text(content: str) -> CookieStatus:
    """Write content that has already passed assess_content."""
    dest = destination_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding='utf-8')
    return assess_content(content, path=str(dest))


def check() -> None:
    print(assess_installed().message)


if __name__ == '__main__':
    check()
