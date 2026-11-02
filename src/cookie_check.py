"""
Non-interactive cookie-file check for the `cookie` CLI subcommand and the GUI.

Reports whether a cookie file is configured/auto-detected and whether it
looks like a valid YouTube cookies export, or prints setup guidance if not.

Usage: python src/cookie_check.py
"""
import os
import shutil
import sys
import tempfile
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


def classify_probe(has_auth_before: bool, has_auth_after: bool, rotation_warning: bool) -> str:
    """What a YouTube request said about a structurally valid cookie file.

    'rotated' is yt-dlp's case: the jar was logged in, then YouTube cleared
    LOGIN_INFO / the auth cookies. 'not_logged_in' means yt-dlp never saw a
    logged-in jar. 'ok' means the session survived the request.
    """
    if has_auth_before and (not has_auth_after or rotation_warning):
        return 'rotated'
    if not has_auth_before:
        return 'not_logged_in'
    return 'ok'


def _rotation_message(path: str | None) -> str:
    loc = f'found at "{path}"' if path else 'uploaded'
    return (
        f'Cookie file {loc} but YouTube rejected the session. '
        'The cookies have been rotated in the browser as a security measure, '
        'so age-restricted downloads will fail with "Sign in to confirm your age".\n'
        + COOKIE_HELP_TEXT
    )


def _not_logged_in_message(path: str | None) -> str:
    loc = f'found at "{path}"' if path else 'uploaded'
    return (
        f'Cookie file {loc} but YouTube does not treat it as a logged-in session '
        '(LOGIN_INFO or SAPISID is missing). Age-restricted downloads will fail '
        'with "Sign in to confirm your age".\n'
        + COOKIE_HELP_TEXT
    )


def probe_rotation(path: Path) -> dict:
    """Ask YouTube, via yt-dlp, whether this export is still a logged-in session.

    Uses a throwaway copy so YouTube's Set-Cookie response cannot rewrite the
    export. Returns outcome 'ok', 'rotated', 'not_logged_in', or 'unreachable'.
    """
    from yt_dlp import YoutubeDL
    from yt_dlp.extractor.youtube import YoutubeIE

    class _Cap:
        def __init__(self):
            self.warnings = []

        def debug(self, msg):
            return None

        def info(self, msg):
            return None

        def warning(self, msg):
            self.warnings.append(str(msg))

        def error(self, msg):
            self.warnings.append(str(msg))

    fd, scratch = tempfile.mkstemp(prefix='web2mp3-cookies-', suffix='.txt')
    os.close(fd)
    try:
        shutil.copyfile(path, scratch)
        log = _Cap()
        ydl = YoutubeDL({
            'cookiefile': scratch,
            'quiet': True,
            'no_warnings': True,
            'logger': log,
            'socket_timeout': 20,
        })
        ie = YoutubeIE(ydl)
        ie._real_initialize()
        before = bool(ie._has_auth_cookies)
        try:
            ie._request_webpage(
                'https://www.youtube.com/',
                video_id='cookie-check',
                note=False,
                errnote=False,
            )
        except Exception as exc:
            return {
                'outcome': 'unreachable',
                'error': type(exc).__name__,
                'has_auth_before': before,
            }
        after = bool(ie._has_auth_cookies)
        warning = any(
            'no longer valid' in item or 'rotated' in item.lower()
            for item in log.warnings
        )
        return {
            'outcome': classify_probe(before, after, warning),
            'has_auth_before': before,
            'has_auth_after': after,
            'rotation_warning': warning,
        }
    finally:
        try:
            os.unlink(scratch)
        except OSError:
            pass


def confirm_youtube_session(status: CookieStatus, cookie_path: Path) -> CookieStatus:
    """Keep a structural pass only if YouTube still accepts the session."""
    if not status.ok:
        return status
    try:
        result = probe_rotation(cookie_path)
    except Exception:
        return status
    outcome = result.get('outcome')
    if outcome == 'rotated':
        return CookieStatus(False, _rotation_message(status.path), status.path)
    if outcome == 'not_logged_in':
        return CookieStatus(False, _not_logged_in_message(status.path), status.path)
    return status


def assess_upload(content: str) -> CookieStatus:
    """Structural check, then the live YouTube session check, before saving."""
    structural = assess_content(content)
    if not structural.ok:
        return structural
    fd, name = tempfile.mkstemp(prefix='web2mp3-cookies-', suffix='.txt')
    os.close(fd)
    temp = Path(name)
    try:
        temp.write_text(content, encoding='utf-8')
        return confirm_youtube_session(structural, temp)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


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
        structural = assess_file(Path(env))
        if not structural.ok:
            return structural
        return confirm_youtube_session(structural, Path(env))
    found = first_cookie_file()
    if found:
        structural = assess_file(found)
        if not structural.ok:
            return structural
        return confirm_youtube_session(structural, found)
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
