"""Tests for spaceload.snapshot.capturer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from spaceload.snapshot.capturer import capture_current


def _make_browser_adapter(name: str, tabs: list[str], available: bool = True) -> MagicMock:
    a = MagicMock()
    a.name = name
    a.is_available.return_value = available
    a.get_open_tabs.return_value = tabs
    return a


def _make_ide_adapter(name: str, projects: list[str], available: bool = True) -> MagicMock:
    a = MagicMock()
    a.name = name
    a.is_available.return_value = available
    a.get_open_projects.return_value = projects
    return a


def _make_terminal_adapter(name: str, sessions, available: bool = True) -> MagicMock:
    a = MagicMock()
    a.name = name
    a.is_available.return_value = available
    a.get_sessions.return_value = sessions
    return a


def _make_session(app: str, directory: str, session_id: str = "") -> MagicMock:
    s = MagicMock()
    s.app = app
    s.directory = directory
    s.session_id = session_id or f"{app}:{directory}"
    return s


class TestCaptureCurrentReturnsValidActions:
    def test_returns_list(self):
        with _empty_env():
            result = capture_current()
        assert isinstance(result, list)

    def test_browser_tabs_captured(self):
        adapter = _make_browser_adapter("chrome", ["https://example.com", "https://github.com"])
        with _patch_browsers([adapter]), _patch_ides([]), _patch_terminals([]), _patch_vpn(None):
            actions = capture_current()

        tab_actions = [a for a in actions if a["type"] == "browser_tab_open"]
        assert len(tab_actions) == 2
        urls = {a["url"] for a in tab_actions}
        assert urls == {"https://example.com", "https://github.com"}
        assert all(a["browser"] == "chrome" for a in tab_actions)

    def test_ide_projects_captured(self):
        adapter = _make_ide_adapter("vscode", ["/Users/tom/code/payments"])
        with _patch_browsers([]), _patch_ides([adapter]), _patch_terminals([]), _patch_vpn(None):
            actions = capture_current()

        ide_actions = [a for a in actions if a["type"] == "ide_project_open"]
        assert len(ide_actions) == 1
        assert ide_actions[0]["client"] == "vscode"
        assert ide_actions[0]["path"] == "/Users/tom/code/payments"

    def test_terminal_sessions_captured(self):
        session = _make_session("iterm2", "/Users/tom/code")
        adapter = _make_terminal_adapter("iterm2", [session])
        with _patch_browsers([]), _patch_ides([]), _patch_terminals([adapter]), _patch_vpn(None):
            actions = capture_current()

        term_actions = [a for a in actions if a["type"] == "terminal_session_open"]
        assert len(term_actions) == 1
        assert term_actions[0]["app"] == "iterm2"
        assert term_actions[0]["directory"] == "/Users/tom/code"

    def test_vpn_captured_when_connected(self):
        from spaceload.adapters.vpn.base import VPNState
        vpn_adapter = MagicMock()
        vpn_adapter.name = "tailscale"
        state = VPNState(connected=True, profile="work", client="tailscale")
        with _patch_browsers([]), _patch_ides([]), _patch_terminals([]), _patch_vpn((vpn_adapter, state)):
            actions = capture_current()

        vpn_actions = [a for a in actions if a["type"] == "vpn_connect"]
        assert len(vpn_actions) == 1
        assert vpn_actions[0]["client"] == "tailscale"
        assert vpn_actions[0]["profile"] == "work"

    def test_no_vpn_when_disconnected(self):
        with _patch_browsers([]), _patch_ides([]), _patch_terminals([]), _patch_vpn(None):
            actions = capture_current()

        vpn_actions = [a for a in actions if a["type"] == "vpn_connect"]
        assert vpn_actions == []

    def test_adapter_error_skipped(self):
        adapter = _make_browser_adapter("chrome", [])
        adapter.get_open_tabs.side_effect = RuntimeError("AppleScript failed")
        with _patch_browsers([adapter]), _patch_ides([]), _patch_terminals([]), _patch_vpn(None):
            actions = capture_current()  # should not raise

        assert isinstance(actions, list)

    def test_all_actions_have_timestamp(self):
        adapter = _make_browser_adapter("chrome", ["https://example.com"])
        with _patch_browsers([adapter]), _patch_ides([]), _patch_terminals([]), _patch_vpn(None):
            actions = capture_current()

        for a in actions:
            assert "timestamp" in a
            assert a["timestamp"]

    def test_blank_urls_filtered(self):
        adapter = _make_browser_adapter("chrome", ["https://example.com", "   ", ""])
        with _patch_browsers([adapter]), _patch_ides([]), _patch_terminals([]), _patch_vpn(None):
            actions = capture_current()

        tab_actions = [a for a in actions if a["type"] == "browser_tab_open"]
        assert len(tab_actions) == 1


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------

from contextlib import contextmanager


@contextmanager
def _patch_browsers(adapters):
    registry = MagicMock()
    registry.available_adapters.return_value = adapters
    with patch("spaceload.snapshot.capturer.BrowserAdapterRegistry", return_value=registry):
        yield


@contextmanager
def _patch_ides(adapters):
    registry = MagicMock()
    registry.available_adapters.return_value = adapters
    with patch("spaceload.snapshot.capturer.IDEAdapterRegistry", return_value=registry):
        yield


@contextmanager
def _patch_terminals(adapters):
    registry = MagicMock()
    registry.available_adapters.return_value = adapters
    with patch("spaceload.snapshot.capturer.TerminalAdapterRegistry", return_value=registry):
        yield


@contextmanager
def _patch_vpn(result):
    registry = MagicMock()
    registry.detect_active.return_value = result
    with patch("spaceload.snapshot.capturer.VPNAdapterRegistry", return_value=registry):
        yield


@contextmanager
def _empty_env():
    with (
        _patch_browsers([]),
        _patch_ides([]),
        _patch_terminals([]),
        _patch_vpn(None),
    ):
        yield
