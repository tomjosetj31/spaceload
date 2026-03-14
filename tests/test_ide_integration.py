"""Integration tests for IDEPoller and replayer IDE action handling."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from loadout.daemon.server import IDEPoller
from loadout.replayer.replayer import Replayer


# ---------------------------------------------------------------------------
# IDEPoller integration tests
# ---------------------------------------------------------------------------

class TestIDEPollerIntegration:
    """Test that IDEPoller correctly detects new projects and appends to the action log."""

    def test_new_project_emits_ide_project_open_event(self):
        """Poller should emit ide_project_open when a new project path appears."""
        actions: list[dict] = []
        poller = IDEPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "vscode"
            call_count += 1
            if call_count == 1:
                adapter.get_open_projects.return_value = ["/home/user/old-project"]
            else:
                adapter.get_open_projects.return_value = [
                    "/home/user/old-project",
                    "/home/user/new-project",
                ]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("loadout.daemon.server.IDEAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "ide_project_open"]
        assert len(open_actions) >= 1
        action = open_actions[0]
        assert action["client"] == "vscode"
        assert action["path"] == "/home/user/new-project"
        assert "timestamp" in action

    def test_no_event_on_first_poll(self):
        """First poll establishes baseline — no events emitted."""
        actions: list[dict] = []
        poller = IDEPoller(actions, poll_interval=0.05)

        adapter = MagicMock()
        adapter.name = "vscode"
        adapter.get_open_projects.return_value = ["/home/user/project"]
        mock_registry = MagicMock()
        mock_registry.available_adapters.return_value = [adapter]

        with patch("loadout.daemon.server.IDEAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.08)
            poller.stop()

        assert actions == []

    def test_no_event_when_projects_stable(self):
        """No events when open projects remain the same across polls."""
        actions: list[dict] = []
        poller = IDEPoller(actions, poll_interval=0.05)

        adapter = MagicMock()
        adapter.name = "cursor"
        adapter.get_open_projects.return_value = ["/home/user/project"]
        mock_registry = MagicMock()
        mock_registry.available_adapters.return_value = [adapter]

        with patch("loadout.daemon.server.IDEAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        assert actions == []

    def test_event_contains_required_fields(self):
        """ide_project_open action must contain type, client, path, timestamp."""
        actions: list[dict] = []
        poller = IDEPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "zed"
            call_count += 1
            if call_count == 1:
                adapter.get_open_projects.return_value = []
            else:
                adapter.get_open_projects.return_value = ["/home/user/zed-project"]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("loadout.daemon.server.IDEAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "ide_project_open"]
        assert open_actions, "Expected at least one ide_project_open action"
        action = open_actions[0]
        assert action["type"] == "ide_project_open"
        assert action["client"] == "zed"
        assert action["path"] == "/home/user/zed-project"
        assert isinstance(action["timestamp"], str)

    def test_poller_handles_adapter_error_gracefully(self):
        """Poller should continue running if an adapter raises."""
        actions: list[dict] = []
        poller = IDEPoller(actions, poll_interval=0.05)

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = RuntimeError("storage read error")

        with patch("loadout.daemon.server.IDEAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.2)
            poller.stop()

        assert actions == []

    def test_multiple_new_projects_emit_multiple_events(self):
        """Each new project path gets its own ide_project_open action."""
        actions: list[dict] = []
        poller = IDEPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "vscode"
            call_count += 1
            if call_count == 1:
                adapter.get_open_projects.return_value = []
            else:
                adapter.get_open_projects.return_value = [
                    "/home/user/project-a",
                    "/home/user/project-b",
                ]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("loadout.daemon.server.IDEAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "ide_project_open"]
        paths = {a["path"] for a in open_actions}
        assert "/home/user/project-a" in paths
        assert "/home/user/project-b" in paths

    def test_multiple_ides_tracked_independently(self):
        """Each IDE gets its own baseline — events are per-client."""
        actions: list[dict] = []
        poller = IDEPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            call_count += 1

            vscode = MagicMock()
            vscode.name = "vscode"
            cursor = MagicMock()
            cursor.name = "cursor"

            if call_count == 1:
                vscode.get_open_projects.return_value = []
                cursor.get_open_projects.return_value = []
            else:
                vscode.get_open_projects.return_value = ["/home/user/vs-project"]
                cursor.get_open_projects.return_value = ["/home/user/cursor-project"]
            return [vscode, cursor]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("loadout.daemon.server.IDEAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "ide_project_open"]
        clients = {a["client"] for a in open_actions}
        assert "vscode" in clients
        assert "cursor" in clients


# ---------------------------------------------------------------------------
# Replayer IDE action tests
# ---------------------------------------------------------------------------

class TestReplayerIDEActions:
    """Test that Replayer correctly handles ide_project_open actions."""

    def _make_mock_registry(self, open_result=True):
        mock_adapter = MagicMock()
        mock_adapter.name = "vscode"
        mock_adapter.open_project.return_value = open_result
        mock_registry = MagicMock()
        mock_registry.get_adapter.return_value = mock_adapter
        return mock_registry, mock_adapter

    def test_replay_ide_project_open_calls_adapter(self, capsys):
        mock_registry, mock_adapter = self._make_mock_registry(open_result=True)

        actions = [
            {
                "type": "ide_project_open",
                "client": "vscode",
                "path": "/home/user/myproject",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test", actions)
        replayer._ide_registry = mock_registry

        replayer.replay()

        mock_registry.get_adapter.assert_called_once_with("vscode")
        mock_adapter.open_project.assert_called_once_with("/home/user/myproject")
        captured = capsys.readouterr()
        assert "ok" in captured.out

    def test_replay_ide_project_open_failure_logs_warning(self, capsys):
        mock_registry, mock_adapter = self._make_mock_registry(open_result=False)

        actions = [
            {
                "type": "ide_project_open",
                "client": "vscode",
                "path": "/home/user/myproject",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test", actions)
        replayer._ide_registry = mock_registry

        replayer.replay()

        captured = capsys.readouterr()
        assert "warn" in captured.out or "failed" in captured.out.lower()

    def test_replay_ide_project_open_unknown_client_skips(self, capsys):
        mock_registry = MagicMock()
        mock_registry.get_adapter.return_value = None

        actions = [
            {
                "type": "ide_project_open",
                "client": "vim",
                "path": "/home/user/myproject",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test", actions)
        replayer._ide_registry = mock_registry

        replayer.replay()  # should not raise

        captured = capsys.readouterr()
        assert "skip" in captured.out.lower() or "warn" in captured.out.lower()

    def test_replay_mixed_browser_and_ide_actions(self, capsys):
        """Replayer handles a mix of browser and IDE actions correctly."""
        mock_browser_adapter = MagicMock()
        mock_browser_adapter.open_url.return_value = True
        mock_browser_registry = MagicMock()
        mock_browser_registry.get_adapter.return_value = mock_browser_adapter

        mock_ide_adapter = MagicMock()
        mock_ide_adapter.open_project.return_value = True
        mock_ide_registry = MagicMock()
        mock_ide_registry.get_adapter.return_value = mock_ide_adapter

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
        ]
        replayer = Replayer("test", actions)
        replayer._browser_registry = mock_browser_registry
        replayer._ide_registry = mock_ide_registry

        replayer.replay()

        mock_browser_adapter.open_url.assert_called_once_with("https://github.com")
        mock_ide_adapter.open_project.assert_called_once_with("/home/user/myproject")
        captured = capsys.readouterr()
        assert "ok" in captured.out

    def test_replay_cursor_project(self, capsys):
        mock_adapter = MagicMock()
        mock_adapter.open_project.return_value = True
        mock_registry = MagicMock()
        mock_registry.get_adapter.return_value = mock_adapter

        actions = [
            {
                "type": "ide_project_open",
                "client": "cursor",
                "path": "/home/user/cursor-project",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test", actions)
        replayer._ide_registry = mock_registry

        replayer.replay()

        mock_registry.get_adapter.assert_called_once_with("cursor")
        mock_adapter.open_project.assert_called_once_with("/home/user/cursor-project")
