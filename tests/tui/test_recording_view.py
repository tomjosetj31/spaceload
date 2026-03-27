"""Tests for spaceload.tui.recording_view."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from spaceload.tui.event_poller import RecordingEvent
from spaceload.tui.recording_view import RecordingView


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_event(adapter: str, action: str, label: str, raw: dict | None = None) -> RecordingEvent:
    return RecordingEvent(
        adapter=adapter,
        action=action,
        label=label,
        timestamp=_now(),
        raw=raw or {},
    )


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestRecordingViewInit:
    def test_starts_empty(self):
        view = RecordingView("my-project")
        assert view.workspace_name == "my-project"
        assert view.browser_tabs == {}
        assert view.ide_projects == {}
        assert view.terminal_sessions == {}
        assert not view.vpn_connected
        assert view.vpn_label == "not connected"
        assert view.total_events == 0

    def test_start_time_is_recent(self):
        before = datetime.now(timezone.utc)
        view = RecordingView("test")
        after = datetime.now(timezone.utc)
        assert before <= view.start_time <= after


# ---------------------------------------------------------------------------
# update_events — browser
# ---------------------------------------------------------------------------

class TestBrowserEvents:
    def test_adds_browser_tab(self):
        view = RecordingView("p")
        evt = _make_event(
            "browser", "tab_opened", "https://example.com",
            raw={"browser": "arc", "url": "https://example.com"},
        )
        view.update_events([evt])
        assert "arc" in view.browser_tabs
        assert len(view.browser_tabs["arc"]) == 1
        assert view.browser_tabs["arc"][0].url == "https://example.com"

    def test_groups_by_browser(self):
        view = RecordingView("p")
        view.update_events([
            _make_event("browser", "tab_opened", "https://a.com", raw={"browser": "arc", "url": "https://a.com"}),
            _make_event("browser", "tab_opened", "https://b.com", raw={"browser": "chrome", "url": "https://b.com"}),
        ])
        assert "arc" in view.browser_tabs
        assert "chrome" in view.browser_tabs

    def test_multiple_tabs_same_browser(self):
        view = RecordingView("p")
        for url in ["https://a.com", "https://b.com", "https://c.com"]:
            view.update_events([
                _make_event("browser", "tab_opened", url, raw={"browser": "arc", "url": url})
            ])
        assert len(view.browser_tabs["arc"]) == 3


# ---------------------------------------------------------------------------
# update_events — IDE
# ---------------------------------------------------------------------------

class TestIDEEvents:
    def test_adds_ide_project(self):
        view = RecordingView("p")
        evt = _make_event(
            "ide", "project_captured", "/Users/tom/myapp",
            raw={"client": "vscode", "path": "/Users/tom/myapp"},
        )
        view.update_events([evt])
        assert "vscode" in view.ide_projects
        assert view.ide_projects["vscode"][0].path == "/Users/tom/myapp"

    def test_groups_by_client(self):
        view = RecordingView("p")
        view.update_events([
            _make_event("ide", "project_captured", "/a", raw={"client": "vscode", "path": "/a"}),
            _make_event("ide", "project_captured", "/b", raw={"client": "cursor", "path": "/b"}),
        ])
        assert "vscode" in view.ide_projects
        assert "cursor" in view.ide_projects


# ---------------------------------------------------------------------------
# update_events — terminal
# ---------------------------------------------------------------------------

class TestTerminalEvents:
    def test_adds_terminal_session(self):
        view = RecordingView("p")
        evt = _make_event(
            "terminal", "session_opened", "/Users/tom/code",
            raw={"app": "iterm2", "directory": "/Users/tom/code"},
        )
        view.update_events([evt])
        assert "iterm2" in view.terminal_sessions
        assert view.terminal_sessions["iterm2"][0].directory == "/Users/tom/code"

    def test_multiple_sessions_same_app(self):
        view = RecordingView("p")
        for d in ["/a", "/b"]:
            view.update_events([
                _make_event("terminal", "session_opened", d, raw={"app": "iterm2", "directory": d})
            ])
        assert len(view.terminal_sessions["iterm2"]) == 2


# ---------------------------------------------------------------------------
# update_events — VPN
# ---------------------------------------------------------------------------

class TestVPNEvents:
    def test_vpn_connect(self):
        view = RecordingView("p")
        evt = _make_event("vpn", "connected", "tailscale (work)")
        view.update_events([evt])
        assert view.vpn_connected
        assert view.vpn_label == "tailscale (work)"

    def test_vpn_disconnect(self):
        view = RecordingView("p")
        view.update_events([_make_event("vpn", "connected", "tailscale")])
        view.update_events([_make_event("vpn", "disconnected", "tailscale")])
        assert not view.vpn_connected
        assert view.vpn_label == "not connected"

    def test_unknown_adapter_increments_count(self):
        view = RecordingView("p")
        evt = _make_event("app", "opened", "Figma")
        view.update_events([evt])
        assert view.total_events == 1


# ---------------------------------------------------------------------------
# Elapsed time
# ---------------------------------------------------------------------------

class TestElapsedTime:
    def test_elapsed_str_format(self):
        view = RecordingView("p")
        elapsed = view.elapsed_str()
        parts = elapsed.split(":")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)

    def test_elapsed_increases_over_time(self):
        view = RecordingView("p")
        t1 = view.elapsed()
        time.sleep(0.05)
        t2 = view.elapsed()
        assert t2 > t1

    def test_elapsed_str_zero_padded(self):
        view = RecordingView("p")
        s = view.elapsed_str()
        h, m, sec = s.split(":")
        assert len(h) == 2
        assert len(m) == 2
        assert len(sec) == 2


# ---------------------------------------------------------------------------
# summary_counts
# ---------------------------------------------------------------------------

class TestSummaryCounts:
    def test_empty_view(self):
        view = RecordingView("p")
        counts = view.summary_counts()
        assert counts["browser"] == {}
        assert counts["ide"] == {}
        assert counts["terminal_count"] == 0
        assert counts["terminal_app"] is None
        assert counts["vpn"] == "not connected"

    def test_with_events(self):
        view = RecordingView("p")
        view.update_events([
            _make_event("browser", "tab_opened", "https://a.com", raw={"browser": "arc", "url": "https://a.com"}),
            _make_event("browser", "tab_opened", "https://b.com", raw={"browser": "arc", "url": "https://b.com"}),
            _make_event("ide", "project_captured", "/x", raw={"client": "vscode", "path": "/x"}),
            _make_event("terminal", "session_opened", "/y", raw={"app": "iterm2", "directory": "/y"}),
            _make_event("terminal", "session_opened", "/z", raw={"app": "iterm2", "directory": "/z"}),
            _make_event("vpn", "connected", "tailscale"),
        ])
        counts = view.summary_counts()
        assert counts["browser"]["arc"] == 2
        assert counts["ide"]["vscode"] == 1
        assert counts["terminal_count"] == 2
        assert counts["terminal_app"] == "iterm2"
        assert counts["vpn"] == "tailscale"
