"""Classify yt-dlp / download exceptions as permanent vs retryable."""
from __future__ import annotations

import re
from typing import Literal

Kind = Literal["permanent", "retryable"]

# Checked first so cookie/bot/network wording wins over a generic "unavailable".
_RETRYABLE_PATTERNS = (
    re.compile(r"sign in to confirm", re.I),
    re.compile(r"not a bot", re.I),
    re.compile(r"age[- ]?restrict", re.I),
    re.compile(r"confirm your age", re.I),
    re.compile(r"cookies?", re.I),
    re.compile(r"http\s*429|\b429\b", re.I),
    re.compile(r"timed?\s*out|timeout", re.I),
    re.compile(r"\bdns\b", re.I),
    re.compile(r"connection (reset|refused|aborted|error)|network is unreachable", re.I),
    re.compile(r"\b50[234]\b|http 5\d\d", re.I),
    re.compile(r"js challenge|n-?sig|deno", re.I),
    re.compile(r"http error 403|status code 403", re.I),
)

_PERMANENT_PATTERNS = (
    re.compile(r"video unavailable", re.I),
    re.compile(r"this video is not available", re.I),
    re.compile(r"private video", re.I),
    re.compile(r"has been removed", re.I),
    re.compile(r"video has been removed", re.I),
    re.compile(r"copyright", re.I),
    re.compile(r"who has blocked it", re.I),
    re.compile(r"account associated with this video has been terminated", re.I),
    re.compile(r"no longer available", re.I),
    re.compile(r"video is unavailable", re.I),
)


def classify_download_error(exc: BaseException | str) -> tuple[Kind, str]:
    """Return (kind, short_reason). Unknown errors default to retryable."""
    text = str(exc)
    for pat in _RETRYABLE_PATTERNS:
        if pat.search(text):
            return "retryable", _short_reason(pat, text)
    for pat in _PERMANENT_PATTERNS:
        if pat.search(text):
            return "permanent", _short_reason(pat, text)
    return "retryable", "unknown"


def _short_reason(pat: re.Pattern, text: str) -> str:
    m = pat.search(text)
    if m:
        return m.group(0).lower()
    return text[:80]
