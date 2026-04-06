"""Tests for spaceload.tui.event_poller."""

from __future__ import annotations

import json
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spaceload.tui.event_poller import EventPoller, RecordingEvent, _raw_to_event


# ---------------------------------------------------------------------------
# _raw_to_event conversion
# ---------------------------------------------------------------------------

class TestRawToEvent:
    def test_browser_tab_open(self):
        raw = {
            "type": "browser_tab_open",
            "browser": "arc",
            "url": "https://example.com",
            "timestamp": "2024-01-01T10:00:00+00:00",
        }
        evt = _raw_to_event(raw)
        assert evt.adapter == "browser"
        assert evt.action == "tab_opened"
        assert evt.label == "https://example.com"
        assert evt.raw["browser"] == "arc"

    def test_ide_project_open(self):
        raw = {
            "type": "ide_project_open",
            "client": "vscode",
            "path": "/Users/tom/code/myapp",
            "timestamp": "2024-01-01T10:00:00+00:00",
        }
        evt = _raw_to_event(raw)
        assert evt.adapter == "ide"
        assert evt.action == "project_captured"
        assert evt.label == "/Users/tom/code/myapp"

    def test_terminal_session_open(self):
        raw = {
            "type": "terminal_session_open",
            "app": "iterm2",
            "directory": "/Users/tom/code",
            "session_id": "s1",
            "timestamp": "2024-01-01T10:00:00+00:00",
        }
        evt = _raw_to_event(raw)
        assert evt.adapter == "terminal"
        assert evt.action == "session_opened"
        assert evt.label == "/Users/tom/code"

    def test_vpn_connect_with_profile(self):
        raw = {
            "type": "vpn_connect",
            "client": "tailscale",
            "profile": "work",
            "timestamp": "2024-01-01T10:00:00+00:00",
        }
        evt = _raw_to_event(raw)
        assert evt.adapter == "vpn"
        assert evt.action == "connected"
        assert "tailscale" in evt.label
        assert "work" in evt.label

    def test_vpn_connect_without_profile(self):
        raw = {
            "type": "vpn_connect",
            "client": "tailscale",
            "timestamp": "2024-01-01T10:00:00+00:00",
        }
        evt = _raw_to_event(raw)
        assert evt.label == "tailscale"

    def test_vpn_disconnect(self):
        raw = {
            "type": "vpn_disconnect",
            "client": "tailscale",
            "timestamp": "2024-01-01T10:00:00+00:00",
        }
        evt = _raw_to_event(raw)
        assert evt.adapter == "vpn"
        assert evt.action == "disconnected"

    def test_app_open(self):
        raw = {
            "type": "app_open",
            "app_name": "Figma",
            "timestamp": "2024-01-01T10:00:00+00:00",
        }
        evt = _raw_to_event(raw)
        assert evt.adapter == "app"
        assert evt.label == "Figma"

    def test_unknown_type(self):
        raw = {"type": "future_type", "timestamp": "2024-01-01T10:00:00+00:00"}
        evt = _raw_to_event(raw)
        assert evt.adapter == "unknown"
        assert evt.action == "future_type"

    def test_missing_timestamp_defaults_to_now(self):
        raw = {"type": "browser_tab_open", "url": "https://x.com"}
        before = datetime.now(timezone.utc)
        evt = _raw_to_event(raw)
        after = datetime.now(timezone.utc)
        assert before <= evt.timestamp <= after

    def test_timestamp_gets_utc_tzinfo(self):
        raw = {
            "type": "browser_tab_open",
            "url": "https://x.com",
            "timestamp": "2024-01-01T10:00:00",  # naive ISO
        }
        evt = _raw_to_event(raw)
        assert evt.timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# EventPoller — daemon not running
# ---------------------------------------------------------------------------

class TestEventPollerNoDaemon:
    def test_returns_empty_list_when_socket_missing(self, tmp_path):
        poller = EventPoller(tmp_path / "missing.sock")
        result = poller.poll()
        assert result == []

    def test_does_not_raise_on_connection_error(self, tmp_path):
        poller = EventPoller(tmp_path / "missing.sock")
        # Should not raise
        for _ in range(3):
            poller.poll()

    def test_offset_stays_zero_on_failure(self, tmp_path):
        poller = EventPoller(tmp_path / "missing.sock")
        poller.poll()
        assert poller._offset == 0


# ---------------------------------------------------------------------------
# EventPoller — with a mock daemon socket
# ---------------------------------------------------------------------------

def _short_sock_path(name: str) -> Path:
    """Return a short Unix socket path (macOS limit is 104 chars)."""
    import tempfile
    return Path(tempfile.mkdtemp()) / f"{name}.sock"


def _start_mock_daemon(sock_path: Path, responses: list[dict]) -> threading.Thread:
    """Start a Unix socket server that serves canned responses."""
    response_iter = iter(responses)

    def _serve():
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(sock_path))
        server.listen(5)
        server.settimeout(2.0)
        try:
            for _ in range(len(responses)):
                try:
                    conn, _ = server.accept()
                    conn.recv(4096)  # consume the request
                    reply = json.dumps(next(response_iter)) + "\n"
                    conn.sendall(reply.encode())
                    conn.close()
                except socket.timeout:
                    break
        finally:
            server.close()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    return t


class TestEventPollerWithMockDaemon:
    def test_returns_events_from_daemon(self):
        sock_path = _short_sock_path("ev1")
        event_raw = {
            "type": "browser_tab_open",
            "browser": "arc",
            "url": "https://example.com",
            "timestamp": "2024-01-01T10:00:00+00:00",
        }
        response = {"status": "ok", "events": [event_raw], "total": 1}
        _start_mock_daemon(sock_path, [response])

        import time
        time.sleep(0.05)  # let server start

        poller = EventPoller(sock_path)
        events = poller.poll()

        assert len(events) == 1
        assert isinstance(events[0], RecordingEvent)
        assert events[0].adapter == "browser"
        assert events[0].label == "https://example.com"

    def test_tracks_offset_correctly(self):
        sock_path = _short_sock_path("ev2")
        responses = [
            {"status": "ok", "events": [{"type": "browser_tab_open", "url": "https://a.com", "timestamp": "2024-01-01T10:00:00+00:00"}], "total": 1},
            {"status": "ok", "events": [{"type": "browser_tab_open", "url": "https://b.com", "timestamp": "2024-01-01T10:00:00+00:00"}], "total": 2},
        ]
        _start_mock_daemon(sock_path, responses)

        import time
        time.sleep(0.05)

        poller = EventPoller(sock_path)
        first = poller.poll()
        assert poller._offset == 1
        second = poller.poll()
        assert poller._offset == 2
        assert len(first) == 1
        assert len(second) == 1

    def test_empty_events_on_error_status(self):
        sock_path = _short_sock_path("ev3")
        _start_mock_daemon(sock_path, [{"status": "error", "reason": "test"}])

        import time
        time.sleep(0.05)

        poller = EventPoller(sock_path)
        events = poller.poll()
        assert events == []

    def test_reset_clears_offset(self, tmp_path):
        poller = EventPoller(tmp_path / "daemon.sock")
        poller._offset = 42
        poller.reset()
        assert poller._offset == 0
