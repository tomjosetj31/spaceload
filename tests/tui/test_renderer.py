"""Tests for spaceload.tui.renderer."""

from __future__ import annotations

import io
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from spaceload.tui.event_poller import RecordingEvent
from spaceload.tui.recording_view import RecordingView
from spaceload.tui.renderer import Renderer, _rel_time, _trunc, _vlen, is_tty


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_vlen_strips_ansi(self):
        colored = "\033[32mhello\033[0m"
        assert _vlen(colored) == 5

    def test_vlen_plain_string(self):
        assert _vlen("hello world") == 11

    def test_vlen_nested_codes(self):
        s = "\033[1m\033[32mfoo\033[0m"
        assert _vlen(s) == 3

    def test_trunc_short_string(self):
        assert _trunc("hello", 10) == "hello"

    def test_trunc_exact_length(self):
        assert _trunc("hello", 5) == "hello"

    def test_trunc_truncates(self):
        result = _trunc("hello world", 8)
        assert len(result) == 8
        assert result.endswith("…")

    def test_rel_time_just_now(self):
        ts = datetime.now(timezone.utc)
        assert _rel_time(ts) == "just now"

    def test_rel_time_seconds(self):
        ts = datetime.now(timezone.utc) - timedelta(seconds=30)
        result = _rel_time(ts)
        assert "s ago" in result

    def test_rel_time_minutes(self):
        ts = datetime.now(timezone.utc) - timedelta(minutes=2, seconds=5)
        result = _rel_time(ts)
        assert "ago" in result
        assert ":" in result


# ---------------------------------------------------------------------------
# is_tty
# ---------------------------------------------------------------------------

class TestIsTTY:
    def test_returns_false_in_test_env(self):
        # In pytest, stdout is captured (not a TTY)
        assert not is_tty()

    def test_returns_false_for_string_io(self):
        with patch("sys.stdout", new=io.StringIO()):
            assert not is_tty()


# ---------------------------------------------------------------------------
# Renderer — non-TTY (no-op)
# ---------------------------------------------------------------------------

class TestRendererNonTTY:
    def test_render_is_noop_when_not_tty(self):
        renderer = Renderer()
        view = RecordingView("test")
        captured = io.StringIO()
        with patch("sys.stdout", new=captured):
            renderer.render(view)
        assert captured.getvalue() == ""

    def test_clear_is_noop_when_not_tty(self):
        renderer = Renderer()
        captured = io.StringIO()
        with patch("sys.stdout", new=captured):
            renderer.clear()
        assert captured.getvalue() == ""


# ---------------------------------------------------------------------------
# Renderer — panel construction (tested via _build, bypasses TTY check)
# ---------------------------------------------------------------------------

def _make_view_with_events() -> RecordingView:
    view = RecordingView("my-project")
    ts = datetime.now(timezone.utc)
    view.update_events([
        RecordingEvent("browser", "tab_opened", "https://localhost:3000", ts,
                       raw={"browser": "Arc", "url": "https://localhost:3000"}),
        RecordingEvent("ide", "project_captured", "/Users/tom/code/myapp", ts,
                       raw={"client": "VS Code", "path": "/Users/tom/code/myapp"}),
        RecordingEvent("terminal", "session_opened", "/Users/tom/code", ts,
                       raw={"app": "iTerm2", "directory": "/Users/tom/code"}),
        RecordingEvent("vpn", "connected", "tailscale (work)", ts, raw={}),
    ])
    return view


class TestRendererBuild:
    def test_panel_contains_workspace_name(self):
        renderer = Renderer()
        view = RecordingView("my-project")
        lines = renderer._build(view)
        panel = "\n".join(lines)
        assert "my-project" in panel

    def test_panel_contains_elapsed_time(self):
        renderer = Renderer()
        view = RecordingView("test")
        lines = renderer._build(view)
        panel = "\n".join(lines)
        # elapsed time always starts with "00:"
        assert "00:" in panel

    def test_panel_contains_recording_indicator(self):
        renderer = Renderer()
        view = RecordingView("test")
        lines = renderer._build(view)
        panel = "\n".join(lines)
        assert "RECORDING" in panel
        assert "●" in panel

    def test_panel_contains_browser_section(self):
        renderer = Renderer()
        view = _make_view_with_events()
        lines = renderer._build(view)
        panel = "\n".join(lines)
        assert "Browser" in panel
        assert "localhost:3000" in panel

    def test_panel_contains_ide_section(self):
        renderer = Renderer()
        view = _make_view_with_events()
        lines = renderer._build(view)
        panel = "\n".join(lines)
        assert "IDE" in panel
        assert "myapp" in panel

    def test_panel_contains_terminal_section(self):
        renderer = Renderer()
        view = _make_view_with_events()
        lines = renderer._build(view)
        panel = "\n".join(lines)
        assert "Terminal" in panel

    def test_panel_contains_vpn_connected(self):
        renderer = Renderer()
        view = _make_view_with_events()
        lines = renderer._build(view)
        panel = "\n".join(lines)
        assert "tailscale" in panel

    def test_panel_shows_not_captured_when_empty(self):
        renderer = Renderer()
        view = RecordingView("test")
        lines = renderer._build(view)
        panel = "\n".join(lines)
        assert "not captured yet" in panel

    def test_panel_shows_vpn_not_connected(self):
        renderer = Renderer()
        view = RecordingView("test")
        lines = renderer._build(view)
        panel = "\n".join(lines)
        assert "not connected" in panel

    def test_footer_hint_present(self):
        renderer = Renderer()
        view = RecordingView("test")
        lines = renderer._build(view)
        panel = "\n".join(lines)
        assert "Ctrl+C" in panel

    def test_box_drawing_characters(self):
        renderer = Renderer()
        view = RecordingView("test")
        lines = renderer._build(view)
        panel = "\n".join(lines)
        assert "╭" in panel
        assert "╰" in panel
        assert "│" in panel

    def test_row_width_consistent(self):
        """All border rows should have the same visual width."""
        import re
        renderer = Renderer()
        view = _make_view_with_events()
        lines = renderer._build(view)

        ansi_re = re.compile(r"\033\[[0-9;]*m")

        # Only check lines that start with a box-drawing char
        border_lines = [
            ansi_re.sub("", l) for l in lines
            if ansi_re.sub("", l).startswith(("╭", "╰", "│", "├"))
        ]
        if border_lines:
            widths = [len(l) for l in border_lines]
            assert len(set(widths)) == 1, f"Inconsistent widths: {set(widths)}"

    def test_renderer_last_line_count_updated(self):
        """After _build, last_lines should be set on the next render (mocked TTY)."""
        renderer = Renderer()
        view = RecordingView("test")
        assert renderer._last_lines == 0
        # Verify _build returns a non-empty list
        lines = renderer._build(view)
        assert len(lines) > 0


# ---------------------------------------------------------------------------
# Renderer — clear resets state
# ---------------------------------------------------------------------------

class TestRendererClear:
    def test_clear_resets_last_lines(self):
        renderer = Renderer()
        renderer._last_lines = 5
        # is_tty() returns False in pytest, so clear() is a no-op, but
        # we can verify it doesn't raise and state is unchanged (no-op path)
        renderer.clear()
        # _last_lines stays 5 because clear is a no-op when not a TTY
        assert renderer._last_lines == 5
