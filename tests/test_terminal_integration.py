"""Integration tests for TerminalPoller and Replayer terminal action handling."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from loadout.daemon.server import TerminalPoller
from loadout.replayer.replayer import Replayer
from loadout.adapters.terminal.base import TerminalSession


# ---------------------------------------------------------------------------
# TerminalPoller integration tests
# ---------------------------------------------------------------------------

class TestTerminalPollerIntegration:
    """Test that TerminalPoller correctly detects new terminal dirs and appends to the action log."""

    def test_new_dir_emits_terminal_session_open_event(self):
        """Poller should emit terminal_session_open when a new session appears."""
        actions: list[dict] = []
        poller = TerminalPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "iterm2"
            call_count += 1
            if call_count == 1:
                # First poll: baseline with one session
                adapter.get_sessions.return_value = [
                    TerminalSession(app="iterm2", directory="/home/user/old-project", session_id="/dev/ttys001")
                ]
            else:
                # Subsequent polls: new session appears
                adapter.get_sessions.return_value = [
                    TerminalSession(app="iterm2", directory="/home/user/old-project", session_id="/dev/ttys001"),
                    TerminalSession(app="iterm2", directory="/home/user/new-project", session_id="/dev/ttys002"),
                ]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("loadout.daemon.server.TerminalAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "terminal_session_open"]
        assert len(open_actions) >= 1
        action = open_actions[0]
        assert action["app"] == "iterm2"
        assert action["directory"] == "/home/user/new-project"
        assert "timestamp" in action

    def test_no_event_on_first_poll(self):
        """First poll establishes baseline — no events emitted."""
        actions: list[dict] = []
        poller = TerminalPoller(actions, poll_interval=0.05)

        adapter = MagicMock()
        adapter.name = "iterm2"
        adapter.get_sessions.return_value = [
            TerminalSession(app="iterm2", directory="/home/user/project", session_id="/dev/ttys001")
        ]
        mock_registry = MagicMock()
        mock_registry.available_adapters.return_value = [adapter]

        with patch("loadout.daemon.server.TerminalAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.08)
            poller.stop()

        assert actions == []

    def test_no_event_when_dirs_stable(self):
        """No events when sessions remain the same across polls."""
        actions: list[dict] = []
        poller = TerminalPoller(actions, poll_interval=0.05)

        adapter = MagicMock()
        adapter.name = "terminal"
        adapter.get_sessions.return_value = [
            TerminalSession(app="terminal", directory="/home/user/project", session_id="/dev/ttys001")
        ]
        mock_registry = MagicMock()
        mock_registry.available_adapters.return_value = [adapter]

        with patch("loadout.daemon.server.TerminalAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        assert actions == []

    def test_event_contains_required_fields(self):
        """terminal_session_open action must contain type, app, directory, timestamp."""
        actions: list[dict] = []
        poller = TerminalPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "kitty"
            call_count += 1
            if call_count == 1:
                adapter.get_sessions.return_value = []
            else:
                adapter.get_sessions.return_value = [
                    TerminalSession(app="kitty", directory="/home/user/kitty-project", session_id="/dev/ttys001")
                ]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("loadout.daemon.server.TerminalAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "terminal_session_open"]
        assert open_actions, "Expected at least one terminal_session_open action"
        action = open_actions[0]
        assert action["type"] == "terminal_session_open"
        assert action["app"] == "kitty"
        assert action["directory"] == "/home/user/kitty-project"
        assert isinstance(action["timestamp"], str)

    def test_poller_handles_registry_error_gracefully(self):
        """Poller should log a warning and return if registry init raises."""
        actions: list[dict] = []
        poller = TerminalPoller(actions, poll_interval=0.05)

        with patch("loadout.daemon.server.TerminalAdapterRegistry", side_effect=RuntimeError("init error")):
            poller.start()
            time.sleep(0.2)
            poller.stop()

        assert actions == []

    def test_multiple_new_dirs_emit_multiple_events(self):
        """Each new session gets its own terminal_session_open action."""
        actions: list[dict] = []
        poller = TerminalPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "iterm2"
            call_count += 1
            if call_count == 1:
                adapter.get_sessions.return_value = []
            else:
                adapter.get_sessions.return_value = [
                    TerminalSession(app="iterm2", directory="/home/user/project-a", session_id="/dev/ttys001"),
                    TerminalSession(app="iterm2", directory="/home/user/project-b", session_id="/dev/ttys002"),
                ]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("loadout.daemon.server.TerminalAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "terminal_session_open"]
        dirs = {a["directory"] for a in open_actions}
        assert "/home/user/project-a" in dirs
        assert "/home/user/project-b" in dirs

    def test_dir_change_emits_terminal_dir_change_event(self):
        """Poller should emit terminal_dir_change when a session changes directory."""
        actions: list[dict] = []
        poller = TerminalPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "iterm2"
            call_count += 1
            if call_count == 1:
                # First poll: baseline
                adapter.get_sessions.return_value = [
                    TerminalSession(app="iterm2", directory="/home/user/old-dir", session_id="/dev/ttys001")
                ]
            else:
                # Subsequent polls: same session, different directory
                adapter.get_sessions.return_value = [
                    TerminalSession(app="iterm2", directory="/home/user/new-dir", session_id="/dev/ttys001")
                ]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("loadout.daemon.server.TerminalAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        change_actions = [a for a in actions if a.get("type") == "terminal_dir_change"]
        assert len(change_actions) >= 1
        action = change_actions[0]
        assert action["app"] == "iterm2"
        assert action["directory"] == "/home/user/new-dir"
        assert action["previous_directory"] == "/home/user/old-dir"
        assert "timestamp" in action


# ---------------------------------------------------------------------------
# Replayer terminal action tests
# ---------------------------------------------------------------------------

class TestReplayerTerminalActions:
    """Test that Replayer correctly handles terminal_session_open actions."""

    def _make_mock_registry(self, open_result=True):
        mock_adapter = MagicMock()
        mock_adapter.name = "iterm2"
        mock_adapter.open_in_dir.return_value = open_result
        mock_registry = MagicMock()
        mock_registry.get_adapter.return_value = mock_adapter
        return mock_registry, mock_adapter

    def test_replay_terminal_session_open_calls_adapter(self, capsys):
        mock_registry, mock_adapter = self._make_mock_registry(open_result=True)

        actions = [
            {
                "type": "terminal_session_open",
                "app": "iterm2",
                "directory": "/home/user/myproject",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test", actions)
        replayer._terminal_registry = mock_registry

        replayer.replay()

        mock_registry.get_adapter.assert_called_once_with("iterm2")
        mock_adapter.open_in_dir.assert_called_once_with("/home/user/myproject")
        captured = capsys.readouterr()
        assert "ok" in captured.out

    def test_replay_terminal_session_open_failure_logs_warning(self, capsys):
        mock_registry, mock_adapter = self._make_mock_registry(open_result=False)

        actions = [
            {
                "type": "terminal_session_open",
                "app": "iterm2",
                "directory": "/home/user/myproject",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test", actions)
        replayer._terminal_registry = mock_registry

        replayer.replay()

        captured = capsys.readouterr()
        assert "warn" in captured.out or "failed" in captured.out.lower()

    def test_replay_terminal_session_open_unknown_app_skips(self, capsys):
        mock_registry = MagicMock()
        mock_registry.get_adapter.return_value = None

        actions = [
            {
                "type": "terminal_session_open",
                "app": "ghostty",
                "directory": "/home/user/myproject",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test", actions)
        replayer._terminal_registry = mock_registry

        replayer.replay()  # should not raise

        captured = capsys.readouterr()
        assert "skip" in captured.out.lower() or "warn" in captured.out.lower()

    def test_replay_mixed_browser_ide_terminal_actions(self, capsys):
        """Replayer handles a mix of browser, IDE and terminal actions correctly."""
        mock_browser_adapter = MagicMock()
        mock_browser_adapter.open_url.return_value = True
        mock_browser_registry = MagicMock()
        mock_browser_registry.get_adapter.return_value = mock_browser_adapter

        mock_ide_adapter = MagicMock()
        mock_ide_adapter.open_project.return_value = True
        mock_ide_registry = MagicMock()
        mock_ide_registry.get_adapter.return_value = mock_ide_adapter

        mock_terminal_adapter = MagicMock()
        mock_terminal_adapter.open_in_dir.return_value = True
        mock_terminal_registry = MagicMock()
        mock_terminal_registry.get_adapter.return_value = mock_terminal_adapter

        actions = [
            {
                "type": "browser_tab_open",
                "browser": "chrome",
                "url": "https://github.com",
                "timestamp": "2026-01-01T00:00:00+00:00",
            },
            {
                "type": "ide_project_open",
                "client": "vscode",
                "path": "/home/user/myproject",
                "timestamp": "2026-01-01T00:00:01+00:00",
            },
            {
                "type": "terminal_session_open",
                "app": "iterm2",
                "directory": "/home/user/myproject",
                "timestamp": "2026-01-01T00:00:02+00:00",
            },
        ]
        replayer = Replayer("test", actions)
        replayer._browser_registry = mock_browser_registry
        replayer._ide_registry = mock_ide_registry
        replayer._terminal_registry = mock_terminal_registry

        replayer.replay()

        mock_browser_adapter.open_url.assert_called_once_with("https://github.com")
        mock_ide_adapter.open_project.assert_called_once_with("/home/user/myproject")
        mock_terminal_adapter.open_in_dir.assert_called_once_with("/home/user/myproject")
        captured = capsys.readouterr()
        assert "ok" in captured.out
