"""Integration tests for BrowserPoller and replayer browser action handling."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from ctx.daemon.server import BrowserPoller
from ctx.replayer.replayer import Replayer


# ---------------------------------------------------------------------------
# BrowserPoller integration tests
# ---------------------------------------------------------------------------

class TestBrowserPollerIntegration:
    """Test that BrowserPoller correctly detects new tabs and appends to the action log."""

    def _make_registry(self, browser_name: str, tabs: list[str]):
        adapter = MagicMock()
        adapter.name = browser_name
        adapter.is_available.return_value = True
        adapter.get_open_tabs.return_value = tabs
        registry = MagicMock()
        registry.available_adapters.return_value = [adapter]
        return registry, adapter

    def test_new_tab_emits_browser_tab_open_event(self):
        """Poller should emit browser_tab_open when a new URL appears."""
        actions: list[dict] = []
        poller = BrowserPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "chrome"
            call_count += 1
            if call_count == 1:
                adapter.get_open_tabs.return_value = ["https://github.com"]
            else:
                adapter.get_open_tabs.return_value = [
                    "https://github.com",
                    "https://example.com",
                ]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("ctx.daemon.server.BrowserAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        tab_open_actions = [a for a in actions if a.get("type") == "browser_tab_open"]
        assert len(tab_open_actions) >= 1
        action = tab_open_actions[0]
        assert action["browser"] == "chrome"
        assert action["url"] == "https://example.com"
        assert "timestamp" in action

    def test_no_event_on_first_poll(self):
        """First poll establishes baseline — no events emitted."""
        actions: list[dict] = []
        poller = BrowserPoller(actions, poll_interval=0.05)

        adapter = MagicMock()
        adapter.name = "chrome"
        adapter.get_open_tabs.return_value = ["https://github.com"]
        mock_registry = MagicMock()
        mock_registry.available_adapters.return_value = [adapter]

        with patch("ctx.daemon.server.BrowserAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.08)  # only one poll cycle
            poller.stop()

        assert actions == []

    def test_no_event_when_tabs_stable(self):
        """No events when open tabs remain the same across polls."""
        actions: list[dict] = []
        poller = BrowserPoller(actions, poll_interval=0.05)

        adapter = MagicMock()
        adapter.name = "chrome"
        adapter.get_open_tabs.return_value = ["https://github.com"]
        mock_registry = MagicMock()
        mock_registry.available_adapters.return_value = [adapter]

        with patch("ctx.daemon.server.BrowserAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        assert actions == []

    def test_event_contains_required_fields(self):
        """browser_tab_open action must contain type, browser, url, timestamp."""
        actions: list[dict] = []
        poller = BrowserPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "safari"
            call_count += 1
            if call_count == 1:
                adapter.get_open_tabs.return_value = []
            else:
                adapter.get_open_tabs.return_value = ["https://apple.com"]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("ctx.daemon.server.BrowserAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "browser_tab_open"]
        assert open_actions, "Expected at least one browser_tab_open action"
        action = open_actions[0]
        assert action["type"] == "browser_tab_open"
        assert action["browser"] == "safari"
        assert action["url"] == "https://apple.com"
        assert isinstance(action["timestamp"], str)

    def test_poller_handles_adapter_error_gracefully(self):
        """Poller should continue running if an adapter raises."""
        actions: list[dict] = []
        poller = BrowserPoller(actions, poll_interval=0.05)

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = RuntimeError("osascript error")

        with patch("ctx.daemon.server.BrowserAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.2)
            poller.stop()

        # No crash, no actions
        assert actions == []

    def test_multiple_new_tabs_emit_multiple_events(self):
        """Each new URL gets its own browser_tab_open action."""
        actions: list[dict] = []
        poller = BrowserPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "chrome"
            call_count += 1
            if call_count == 1:
                adapter.get_open_tabs.return_value = []
            else:
                adapter.get_open_tabs.return_value = [
                    "https://github.com",
                    "https://linear.app",
                ]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("ctx.daemon.server.BrowserAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "browser_tab_open"]
        urls = {a["url"] for a in open_actions}
        assert "https://github.com" in urls
        assert "https://linear.app" in urls


# ---------------------------------------------------------------------------
# Replayer browser action tests
# ---------------------------------------------------------------------------

class TestReplayerBrowserActions:
    """Test that Replayer correctly handles browser_tab_open actions."""

    def _make_mock_registry(self, open_result=True):
        mock_adapter = MagicMock()
        mock_adapter.name = "chrome"
        mock_adapter.open_url.return_value = open_result
        mock_registry = MagicMock()
        mock_registry.get_adapter.return_value = mock_adapter
        return mock_registry, mock_adapter

    def test_replay_browser_tab_open_calls_adapter(self, capsys):
        mock_registry, mock_adapter = self._make_mock_registry(open_result=True)

        actions = [
            {
                "type": "browser_tab_open",
                "browser": "chrome",
                "url": "https://github.com",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test", actions)
        replayer._browser_registry = mock_registry

        replayer.replay()

        mock_registry.get_adapter.assert_called_once_with("chrome")
        mock_adapter.open_url.assert_called_once_with("https://github.com")
        captured = capsys.readouterr()
        assert "ok" in captured.out

    def test_replay_browser_tab_open_failure_logs_warning(self, capsys):
        mock_registry, mock_adapter = self._make_mock_registry(open_result=False)

        actions = [
            {
                "type": "browser_tab_open",
                "browser": "chrome",
                "url": "https://github.com",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test", actions)
        replayer._browser_registry = mock_registry

        replayer.replay()

        captured = capsys.readouterr()
        assert "warn" in captured.out or "failed" in captured.out.lower()

    def test_replay_browser_tab_open_unknown_browser_uses_default(self, capsys):
        """Falls back to `open` command when adapter is not found."""
        mock_registry = MagicMock()
        mock_registry.get_adapter.return_value = None

        actions = [
            {
                "type": "browser_tab_open",
                "browser": "firefox",
                "url": "https://mozilla.org",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test", actions)
        replayer._browser_registry = mock_registry

        with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            replayer.replay()

        # Should have called `open <url>` as fallback
        call_args = mock_run.call_args[0][0]
        assert "open" in call_args
        assert "https://mozilla.org" in call_args

    def test_replay_browser_tab_open_unknown_browser_fallback_failure(self, capsys):
        mock_registry = MagicMock()
        mock_registry.get_adapter.return_value = None

        actions = [
            {
                "type": "browser_tab_open",
                "browser": "firefox",
                "url": "https://mozilla.org",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test", actions)
        replayer._browser_registry = mock_registry

        with patch("subprocess.run", return_value=MagicMock(returncode=1)):
            replayer.replay()  # should not raise

        captured = capsys.readouterr()
        assert "warn" in captured.out or "failed" in captured.out.lower()

    def test_replay_mixed_vpn_and_browser_actions(self, capsys):
        """Replayer handles a mix of VPN and browser actions correctly."""
        mock_vpn_adapter = MagicMock()
        mock_vpn_adapter.connect.return_value = True
        mock_vpn_registry = MagicMock()
        mock_vpn_registry.get_adapter.return_value = mock_vpn_adapter

        mock_browser_adapter = MagicMock()
        mock_browser_adapter.open_url.return_value = True
        mock_browser_registry = MagicMock()
        mock_browser_registry.get_adapter.return_value = mock_browser_adapter

        actions = [
            {
                "type": "vpn_connect",
                "client": "tailscale",
                "profile": "mynet",
                "timestamp": "2026-01-01T00:00:00+00:00",
            },
            {
                "type": "browser_tab_open",
                "browser": "chrome",
                "url": "https://internal.corp.com",
                "timestamp": "2026-01-01T00:00:01+00:00",
            },
        ]
        replayer = Replayer("test", actions)
        replayer._registry = mock_vpn_registry
        replayer._browser_registry = mock_browser_registry

        replayer.replay()

        mock_vpn_adapter.connect.assert_called_once()
        mock_browser_adapter.open_url.assert_called_once_with("https://internal.corp.com")
