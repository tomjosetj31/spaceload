"""Mozilla Firefox browser adapter.

Firefox doesn't support AppleScript for tab access on macOS, so this adapter
uses a different approach:
- Reads the session recovery files to get open tabs
- Uses 'open' command to open URLs

Note: This requires Firefox to be running and have session recovery enabled.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from loadout.adapters.browser.base import BrowserAdapter

logger = logging.getLogger(__name__)


def _find_firefox_profile_dir() -> Path | None:
    """Find the default Firefox profile directory on macOS."""
    profiles_dir = Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"
    
    if not profiles_dir.exists():
        return None
    
    # Look for default profile (usually ends with .default or .default-release)
    for profile in profiles_dir.iterdir():
        if profile.is_dir() and (".default" in profile.name):
            return profile
    
    # Fall back to first profile found
    for profile in profiles_dir.iterdir():
        if profile.is_dir():
            return profile
    
    return None


def _read_session_store(profile_dir: Path) -> list[str]:
    """Read open tab URLs from Firefox session store.
    
    Firefox stores session data in sessionstore-backups/recovery.jsonlz4
    or sessionstore.jsonlz4. The .jsonlz4 format is JSON compressed with LZ4.
    
    For simplicity, we also check for recovery.js (older format) and
    use a fallback approach with AppleScript.
    """
    urls = []
    
    # Try recovery.jsonlz4 first (current session)
    recovery_file = profile_dir / "sessionstore-backups" / "recovery.jsonlz4"
    
    if recovery_file.exists():
        try:
            # Firefox uses Mozilla's custom lz4 format with a header
            # We need to decompress it - try using Python lz4 if available
            urls = _parse_jsonlz4(recovery_file)
            if urls:
                return urls
        except Exception as e:
            logger.debug("Firefox: failed to parse recovery.jsonlz4: %s", e)
    
    # Try sessionstore.jsonlz4 (backup)
    session_file = profile_dir / "sessionstore.jsonlz4"
    if session_file.exists():
        try:
            urls = _parse_jsonlz4(session_file)
            if urls:
                return urls
        except Exception as e:
            logger.debug("Firefox: failed to parse sessionstore.jsonlz4: %s", e)
    
    return urls


def _parse_jsonlz4(filepath: Path) -> list[str]:
    """Parse Mozilla's jsonlz4 format and extract tab URLs.
    
    The format is: 8-byte header "mozLz40\0" + lz4 compressed JSON
    """
    try:
        import lz4.block
    except ImportError:
        logger.debug("Firefox: lz4 module not available, can't read session store")
        return []
    
    with open(filepath, "rb") as f:
        data = f.read()
    
    # Check for mozLz4 header
    if not data.startswith(b"mozLz40\0"):
        logger.debug("Firefox: invalid jsonlz4 header")
        return []
    
    # Decompress (skip 8-byte header)
    try:
        decompressed = lz4.block.decompress(data[8:])
        session = json.loads(decompressed)
    except Exception as e:
        logger.debug("Firefox: failed to decompress/parse session data: %s", e)
        return []
    
    # Extract URLs from session data
    urls = []
    for window in session.get("windows", []):
        for tab in window.get("tabs", []):
            entries = tab.get("entries", [])
            if entries:
                # Get the current entry (last in history)
                current_idx = tab.get("index", len(entries)) - 1
                if 0 <= current_idx < len(entries):
                    url = entries[current_idx].get("url", "")
                    if url:
                        urls.append(url)
    
    return urls


class FirefoxAdapter(BrowserAdapter):
    """Adapter for Mozilla Firefox on macOS.
    
    Uses session recovery files to read open tabs since Firefox
    doesn't support AppleScript for tab access.
    """

    def __init__(self) -> None:
        self._profile_dir = _find_firefox_profile_dir()

    @property
    def name(self) -> str:
        return "firefox"

    def is_available(self) -> bool:
        # Check if Firefox is running
        result = subprocess.run(
            ["pgrep", "-x", "firefox"],
            capture_output=True,
        )
        if result.returncode == 0:
            return True
        
        # Also check for "Firefox" (different process name on some systems)
        result = subprocess.run(
            ["pgrep", "-xi", "firefox"],
            capture_output=True,
        )
        return result.returncode == 0

    def get_open_tabs(self) -> list[str]:
        """Get open tab URLs from Firefox session store."""
        if self._profile_dir is None:
            logger.debug("Firefox: no profile directory found")
            return []
        
        urls = _read_session_store(self._profile_dir)
        logger.debug("Firefox: found %d tabs", len(urls))
        return urls

    def open_url(self, url: str) -> bool:
        """Open a URL in Firefox."""
        result = subprocess.run(
            ["open", "-a", "Firefox", url],
            capture_output=True,
        )
        return result.returncode == 0
