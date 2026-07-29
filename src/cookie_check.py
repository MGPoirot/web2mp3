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

    if '__Secure-1PSID' not in content:
        print(f'Cookie file found at "{path}" but looks incomplete '
              f'(missing "__Secure-1PSID") — age-restricted downloads may fail.')
        print(COOKIE_HELP_TEXT)
        return

    print(f'Cookie file looks valid: "{path}"')


if __name__ == '__main__':
    check()
