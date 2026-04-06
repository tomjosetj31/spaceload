"""Polls the daemon socket for new recording events.

The daemon accumulates actions in memory and exposes them via the
``events`` socket command. EventPoller tracks the current offset so
each call to poll() returns only new events since the last call.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RecordingEvent:
    adapter: str       # "browser", "ide", "terminal", "vpn", "app"
    action: str        # "tab_opened", "project_captured", "session_opened", etc.
    label: str         # human-readable description for display
    timestamp: datetime
    raw: dict = field(default_factory=dict, repr=False)


def _raw_to_event(raw: dict) -> RecordingEvent:
    """Convert a raw action dict to a RecordingEvent."""
    t = raw.get("type", "")
    try:
        ts_str = raw.get("timestamp", "")
        ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        ts = datetime.now(timezone.utc)

    if t == "browser_tab_open":
        return RecordingEvent(
            adapter="browser",
            action="tab_opened",
            label=raw.get("url", ""),
            timestamp=ts,
            raw=raw,
        )
    if t == "ide_project_open":
        return RecordingEvent(
            adapter="ide",
            action="project_captured",
            label=raw.get("path", ""),
            timestamp=ts,
            raw=raw,
        )
    if t == "terminal_session_open":
        return RecordingEvent(
            adapter="terminal",
            action="session_opened",
            label=raw.get("directory", ""),
            timestamp=ts,
            raw=raw,
        )
    if t == "vpn_connect":
        client = raw.get("client", "vpn")
        profile = raw.get("profile")
        label = f"{client} ({profile})" if profile else client
        return RecordingEvent(
            adapter="vpn",
            action="connected",
            label=label,
            timestamp=ts,
            raw=raw,
        )
    if t == "vpn_disconnect":
        return RecordingEvent(
            adapter="vpn",
            action="disconnected",
            label=raw.get("client", "vpn"),
            timestamp=ts,
            raw=raw,
        )
    if t == "app_open":
        return RecordingEvent(
            adapter="app",
            action="opened",
            label=raw.get("app_name", ""),
            timestamp=ts,
            raw=raw,
        )
    return RecordingEvent(
        adapter="unknown",
        action=t,
        label=raw.get("app_name", raw.get("url", raw.get("path", str(raw)))),
        timestamp=ts,
        raw=raw,
    )


class EventPoller:
    """Polls the daemon Unix socket for new recording events.

    Tracks an offset into the daemon's action list and fetches only
    actions that arrived since the previous successful poll.

    Returns an empty list — rather than raising — when the daemon is
    unreachable, so the TUI can keep rendering without crashing.
    """

    def __init__(self, socket_path: Path, poll_interval: float = 0.5) -> None:
        self._socket_path = socket_path
        self.poll_interval = poll_interval
        self._offset: int = 0

    def poll(self) -> list[RecordingEvent]:
        """Return new events since the last successful poll."""
        try:
            payload = (json.dumps({"command": "events", "since": self._offset}) + "\n").encode()
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.settimeout(1.0)
                sock.connect(str(self._socket_path))
                sock.sendall(payload)
                data = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break
            finally:
                sock.close()

            response = json.loads(data.decode().strip())
            if response.get("status") != "ok":
                return []

            new_events = response.get("events", [])
            self._offset = response.get("total", self._offset)
            return [_raw_to_event(e) for e in new_events]

        except Exception:
            return []

    def reset(self) -> None:
        """Reset the polling offset back to zero."""
        self._offset = 0
