"""Tests for spaceload.tui.summary_view."""

from __future__ import annotations

import io
import sys
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from spaceload.tui.event_poller import RecordingEvent
from spaceload.tui.recording_view import RecordingView
from spaceload.tui.summary_view import show_summary


def _ts() -> datetime:
    return datetime.now(timezone.utc)


def _populated_view() -> RecordingView:
    view = RecordingView("my-project")
    view.update_events([
        RecordingEvent("browser", "tab_opened", "https://a.com", _ts(),
                       raw={"browser": "Arc", "url": "https://a.com"}),
        RecordingEvent("browser", "tab_opened", "https://b.com", _ts(),
                       raw={"browser": "Arc", "url": "https://b.com"}),
        RecordingEvent("browser", "tab_opened", "https://c.com", _ts(),
                       raw={"browser": "Arc", "url": "https://c.com"}),
        RecordingEvent("ide", "project_captured", "/Users/tom/payments", _ts(),
                       raw={"client": "VS Code", "path": "/Users/tom/payments"}),
        RecordingEvent("terminal", "session_opened", "/Users/tom/payments", _ts(),
                       raw={"app": "iTerm2", "directory": "/Users/tom/payments"}),
        RecordingEvent("terminal", "session_opened", "/Users/tom/payments/frontend", _ts(),
                       raw={"app": "iTerm2", "directory": "/Users/tom/payments/frontend"}),
        RecordingEvent("terminal", "session_opened", "/Users/tom/payments/scripts", _ts(),
                       raw={"app": "iTerm2", "directory": "/Users/tom/payments/scripts"}),
        RecordingEvent("vpn", "connected", "tailscale (work)", _ts(), raw={}),
    ])
    return view


class TestShowSummary:
    def _capture(self, view: RecordingView, count: int = 10) -> str:
        buf = io.StringIO()
        with patch("sys.stdout", new=buf):
            show_summary(view.workspace_name, view, count)
        return buf.getvalue()

    def test_includes_workspace_name(self):
        view = RecordingView("my-project")
        output = self._capture(view)
        assert "my-project" in output

    def test_includes_duration(self):
        view = RecordingView("test")
        output = self._capture(view)
        assert "Duration:" in output
        assert "00:" in output

    def test_includes_browser_count(self):
        view = _populated_view()
        output = self._capture(view)
        assert "3" in output  # 3 tabs
        assert "Arc" in output

    def test_includes_ide_info(self):
        view = _populated_view()
        output = self._capture(view)
        assert "VS Code" in output

    def test_includes_terminal_count(self):
        view = _populated_view()
        output = self._capture(view)
        assert "3" in output  # 3 sessions
        assert "iTerm2" in output

    def test_includes_vpn_label(self):
        view = _populated_view()
        output = self._capture(view)
        assert "tailscale" in output

    def test_includes_action_count(self):
        view = RecordingView("p")
        output = self._capture(view, count=42)
        assert "42" in output

    def test_includes_run_command(self):
        view = RecordingView("my-project")
        output = self._capture(view)
        assert "spaceload run my-project" in output

    def test_empty_view_shows_none(self):
        view = RecordingView("empty")
        output = self._capture(view)
        assert "none" in output.lower()

    def test_vpn_not_connected_shown(self):
        view = RecordingView("test")
        output = self._capture(view)
        assert "not connected" in output

    def test_single_browser_tab_singular(self):
        view = RecordingView("p")
        view.update_events([
            RecordingEvent("browser", "tab_opened", "https://x.com", _ts(),
                           raw={"browser": "Safari", "url": "https://x.com"}),
        ])
        output = self._capture(view)
        # Singular "tab" not "tabs"
        assert "Browser tab:" in output or "1 (Safari)" in output

    def test_plural_sessions(self):
        view = RecordingView("p")
        for d in ["/a", "/b"]:
            view.update_events([
                RecordingEvent("terminal", "session_opened", d, _ts(),
                               raw={"app": "Warp", "directory": d}),
            ])
        output = self._capture(view)
        assert "2" in output
        assert "Warp" in output
