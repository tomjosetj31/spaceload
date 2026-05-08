"""URL pattern matching for spaceload focus --keep patterns."""

from __future__ import annotations

import fnmatch
from urllib.parse import urlparse


def _hostname(url: str) -> str:
    """Return the hostname of a URL, or the raw string if parsing fails."""
    try:
        return urlparse(url).hostname or url
    except Exception:
        return url


def matches(url: str, pattern: str) -> bool:
    """Return True if *url* matches *pattern*.

    Pattern forms supported:
    - Wildcard domain:  ``*.notion.so``   → any URL whose hostname ends with ``.notion.so``
    - Bare domain:      ``github.com``    → any URL on ``github.com`` or any subdomain
    - URL substring:    ``/docs``         → any URL containing the string
    - Full fnmatch:     ``https://a.com/b/*``
    """
    host = _hostname(url)

    # Wildcard domain pattern (*.example.com)
    if pattern.startswith("*."):
        suffix = pattern[1:]  # ".example.com"
        return host == suffix[1:] or host.endswith(suffix)

    # Bare domain — match exact host or any subdomain
    if "/" not in pattern and ":" not in pattern:
        return host == pattern or host.endswith("." + pattern)

    # Full fnmatch pattern (supports * and ?)
    if fnmatch.fnmatch(url, pattern):
        return True

    # Substring fallback
    return pattern in url


def any_pattern_matches(url: str, patterns: list[str]) -> bool:
    """Return True if *url* matches any pattern in *patterns*."""
    return any(matches(url, p) for p in patterns)
