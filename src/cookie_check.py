"""
Non-interactive cookie-file check for the `cookie` CLI subcommand.

Reports whether a cookie file is configured/auto-detected and whether it
looks like a valid YouTube cookies export, or prints setup guidance if not.

Usage: python src/cookie_check.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from initialize import cookie_file, COOKIE_HELP_TEXT  # noqa: E402

# Cookies YouTube only sets for a signed-in session. A file can be full of
# VISITOR_INFO1_LIVE/PREF/SOCS entries and still be signed out, so presence of
# these specifically is what separates "exported while logged in" from "not".
LOGIN_COOKIES = ('__Secure-1PSID', '__Secure-3PSID')


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


def check() -> None:
    if not cookie_file:
        print(COOKIE_HELP_TEXT)
        return

    path = Path(cookie_file)
    if not path.is_file():
        print(f'Configured cookie file does not exist: "{path}"')
        print(COOKIE_HELP_TEXT)
        return

    content = path.read_text(errors='replace')
    if not content.strip():
        print(f'Cookie file is empty: "{path}"')
        print(COOKIE_HELP_TEXT)
        return

    names = cookie_names(content)
    missing = [c for c in LOGIN_COOKIES if c not in names]
    if missing:
        print(f'Cookie file found at "{path}" but it is not logged in '
              f'(missing {", ".join(missing)}) — age-restricted downloads '
              f'will fail with "Sign in to confirm your age".')
        if names:
            print(f'It only holds {len(names)} non-login cookies, which is what '
                  f'a signed-out or expired session looks like.')
        print(COOKIE_HELP_TEXT)
        return

    print(f'Cookie file looks valid: "{path}"')


if __name__ == '__main__':
    check()
