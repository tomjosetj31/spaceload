"""TablePlus adapter for spaceload."""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
from pathlib import Path
from urllib.parse import quote

from spaceload.adapters.tools.base import ToolAdapter

logger = logging.getLogger(__name__)

_APP_SUPPORT = Path.home() / "Library" / "Application Support" / "com.tinyapp.TablePlus" / "Data"
_CONNECTIONS_DB = _APP_SUPPORT / "Connections"

# AppleScript to read the front TablePlus window title (shows active connection)
_GET_WINDOW_TITLE_SCRIPT = """\
tell application "System Events"
    if exists (process "TablePlus") then
        tell process "TablePlus"
            if (count of windows) > 0 then
                return name of front window
            end if
        end tell
    end if
    return ""
end tell
"""


def _get_active_connection_from_applescript() -> str | None:
    """Return the active connection name from the TablePlus window title."""
    try:
        result = subprocess.run(
            ["osascript", "-e", _GET_WINDOW_TITLE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=5,
        )
        title = result.stdout.strip()
        if not title:
            return None
        # TablePlus window titles are typically "ConnectionName (database)" or just "ConnectionName"
        # Strip the "(database)" suffix if present
        if " (" in title:
            title = title[: title.rfind(" (")]
        return title or None
    except (subprocess.SubprocessError, OSError) as exc:
        logger.debug("TablePlusAdapter: AppleScript error: %s", exc)
        return None


def _get_most_recent_connection_from_db() -> str | None:
    """Return the most recently used connection name from the TablePlus SQLite DB."""
    if not _CONNECTIONS_DB.exists():
        return None
    try:
        with sqlite3.connect(str(_CONNECTIONS_DB)) as conn:
            cur = conn.execute("SELECT data FROM connections ORDER BY rowid DESC LIMIT 20")
            rows = cur.fetchall()
        for (data_str,) in rows:
            try:
                info = json.loads(data_str) if isinstance(data_str, str) else data_str
                name = info.get("ConnectionName") or info.get("Name") or info.get("name")
                if name:
                    return str(name)
            except (json.JSONDecodeError, TypeError):
                continue
    except (sqlite3.Error, OSError) as exc:
        logger.debug("TablePlusAdapter: DB read error: %s", exc)
    return None


class TablePlusAdapter(ToolAdapter):
    """Adapter for TablePlus: records the active DB connection and reopens it."""

    name = "tableplus"
    action_type = "tableplus_connection_open"

    def is_available(self) -> bool:
        """Return True if the TablePlus data directory exists."""
        return _APP_SUPPORT.exists()

    def detect(self) -> dict | None:
        """Return the active connection name, or None if unavailable.

        Prefers the live window title (AppleScript); falls back to the
        most recently listed entry in the connections database.
        """
        if not self.is_available():
            return None

        connection_name = _get_active_connection_from_applescript()
        if not connection_name:
            connection_name = _get_most_recent_connection_from_db()
        if not connection_name:
            return None

        return {"connection_name": connection_name}

    def apply(self, state: dict) -> bool:
        """Open TablePlus, attempting to navigate to the recorded connection.

        Tries the ``tableplus://open?name=<name>`` URL scheme first;
        falls back to launching the app with no specific connection.
        """
        connection_name = state.get("connection_name", "")
        if connection_name:
            try:
                encoded = quote(connection_name, safe="")
                result = subprocess.run(
                    ["open", f"tableplus://open?name={encoded}"],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return True
                logger.debug(
                    "TablePlusAdapter.apply(): URL scheme failed, falling back to open -a"
                )
            except (subprocess.SubprocessError, OSError) as exc:
                logger.debug("TablePlusAdapter.apply(): URL scheme error: %s", exc)

        # Fallback: just open the app
        try:
            result = subprocess.run(
                ["open", "-a", "TablePlus"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("TablePlusAdapter.apply() failed: %s", exc)
            return False
