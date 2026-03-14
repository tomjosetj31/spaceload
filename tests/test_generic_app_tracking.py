"""Tests for WindowSnapshotPoller (generic app tracking) and TunnelblickAdapter."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from ctx.adapters.vpn.tunnelblick import TunnelblickAdapter
from ctx.adapters.wm.base import WMWindow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_window(window_id: int, app_name: str, workspace: str = "1") -> WMWindow:
    return WMWindow(window_id=window_id, workspace=workspace, app_name=app_name)


def _proc(stdout="", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


# ---------------------------------------------------------------------------
# WindowSnapshotPoller
# ---------------------------------------------------------------------------

class TestWindowSnapshotPoller:
    def _make_poller(self):
        # Import here so patches in individual tests apply cleanly
        from ctx.daemon.server import WindowSnapshotPoller
        actions = []
        poller = WindowSnapshotPoller(actions, poll_interval=0.05)
        return poller, actions

    def test_new_app_recorded(self):
        poller, actions = self._make_poller()
        mock_wm = MagicMock()
        # Initial snapshot: empty
        mock_wm.list_windows.return_value = []
        poller._wm = mock_wm
        poller._seen_ids = set()

        # New window appears
        mock_wm.list_windows.return_value = [_make_window(42, "Microsoft Teams", "1")]
        poller._poll_wm()

        assert len(actions) == 1
        assert actions[0]["type"] == "app_open"
        assert actions[0]["app_name"] == "Microsoft Teams"
        assert actions[0]["workspace"] == "1"

    def test_managed_app_skipped(self):
        poller, actions = self._make_poller()
        mock_wm = MagicMock()
        mock_wm.list_windows.return_value = []
        poller._wm = mock_wm
        poller._seen_ids = set()

        # Chrome is managed by BrowserPoller — should be skipped
        mock_wm.list_windows.return_value = [_make_window(10, "Google Chrome", "2")]
        poller._poll_wm()

        assert actions == []

    def test_all_managed_apps_skipped(self):
        """Every app in _MANAGED_OS_NAMES is ignored."""
        from ctx.daemon.server import WindowSnapshotPoller
        poller, actions = self._make_poller()
        mock_wm = MagicMock()
        poller._wm = mock_wm
        poller._seen_ids = set()

        managed = list(WindowSnapshotPoller._MANAGED_OS_NAMES)
        windows = [_make_window(i, name, "1") for i, name in enumerate(managed, start=1)]
        mock_wm.list_windows.return_value = windows
        poller._poll_wm()

        assert actions == []

    def test_existing_window_not_rerecorded(self):
        poller, actions = self._make_poller()
        mock_wm = MagicMock()
        poller._wm = mock_wm
        # Seed window 42 as already seen
        poller._seen_ids = {42}
        mock_wm.list_windows.return_value = [_make_window(42, "Slack", "2")]

        poller._poll_wm()

        assert actions == []

    def test_multiple_new_apps(self):
        poller, actions = self._make_poller()
        mock_wm = MagicMock()
        poller._wm = mock_wm
        poller._seen_ids = set()

        mock_wm.list_windows.return_value = [
            _make_window(1, "Slack", "2"),
            _make_window(2, "Microsoft Teams", "1"),
            _make_window(3, "Firefox", "Q"),
        ]
        poller._poll_wm()

        assert len(actions) == 3
        app_names = {a["app_name"] for a in actions}
        assert app_names == {"Slack", "Microsoft Teams", "Firefox"}

    def test_second_poll_does_not_re_record(self):
        poller, actions = self._make_poller()
        mock_wm = MagicMock()
        poller._wm = mock_wm
        poller._seen_ids = set()

        mock_wm.list_windows.return_value = [_make_window(1, "Slack", "2")]
        poller._poll_wm()
        poller._poll_wm()  # same window, second poll

        assert len(actions) == 1  # only recorded once

    def test_no_wm_fallback_records_new_app(self):
        poller, actions = self._make_poller()
        poller._wm = None
        poller._seen_apps = {"Finder", "Safari"}  # pre-existing

        with patch("ctx.daemon.server._get_running_foreground_apps",
                   return_value={"Finder", "Safari", "Slack"}):
            poller._poll_fallback()

        assert len(actions) == 1
        assert actions[0]["app_name"] == "Slack"
        assert actions[0]["type"] == "app_open"
        assert "workspace" not in actions[0]

    def test_no_wm_fallback_skips_managed(self):
        poller, actions = self._make_poller()
        poller._wm = None
        poller._seen_apps = set()

        with patch("ctx.daemon.server._get_running_foreground_apps",
                   return_value={"Google Chrome", "Slack"}):
            poller._poll_fallback()

        assert len(actions) == 1
        assert actions[0]["app_name"] == "Slack"

    def test_no_wm_fallback_updates_seen_apps(self):
        poller, actions = self._make_poller()
        poller._wm = None
        poller._seen_apps = set()

        with patch("ctx.daemon.server._get_running_foreground_apps",
                   return_value={"Slack", "Teams"}):
            poller._poll_fallback()
            poller._poll_fallback()  # second poll — same apps, nothing new

        assert len(actions) == 2  # Slack + Teams, but only once each

    def test_action_has_timestamp(self):
        poller, actions = self._make_poller()
        mock_wm = MagicMock()
        poller._wm = mock_wm
        poller._seen_ids = set()
        mock_wm.list_windows.return_value = [_make_window(1, "Photoshop", "3")]

        poller._poll_wm()

        assert "timestamp" in actions[0]

    def test_workspace_attached_to_action(self):
        poller, actions = self._make_poller()
        mock_wm = MagicMock()
        poller._wm = mock_wm
        poller._seen_ids = set()
        mock_wm.list_windows.return_value = [_make_window(99, "Blender", "5")]

        poller._poll_wm()

        assert actions[0]["workspace"] == "5"


# ---------------------------------------------------------------------------
# TunnelblickAdapter
# ---------------------------------------------------------------------------

class TestTunnelblickAdapter:
    def setup_method(self):
        self.adapter = TunnelblickAdapter()

    def test_name(self):
        assert self.adapter.name == "tunnelblick"

    def test_is_available_true(self):
        with patch("os.path.isdir", return_value=True):
            assert self.adapter.is_available() is True

    def test_is_available_false(self):
        with patch("os.path.isdir", return_value=False):
            assert self.adapter.is_available() is False

    def test_detect_not_available(self):
        with patch("os.path.isdir", return_value=False):
            assert self.adapter.detect() is None

    def test_detect_connected(self):
        with patch("os.path.isdir", return_value=True), \
             patch("subprocess.run") as mock_run:
            # First call returns config names, second returns state
            mock_run.side_effect = [
                _proc(stdout="Home VPN"),
                _proc(stdout="CONNECTED"),
            ]
            state = self.adapter.detect()

        assert state is not None
        assert state.connected is True
        assert state.profile == "Home VPN"
        assert state.client == "tunnelblick"

    def test_detect_disconnected(self):
        with patch("os.path.isdir", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _proc(stdout="Home VPN"),
                _proc(stdout="DISCONNECTED"),
            ]
            state = self.adapter.detect()

        assert state is not None
        assert state.connected is False

    def test_detect_no_configurations(self):
        with patch("os.path.isdir", return_value=True), \
             patch("subprocess.run", return_value=_proc(stdout="")):
            state = self.adapter.detect()

        assert state is not None
        assert state.connected is False

    def test_connect_success(self):
        with patch("os.path.isdir", return_value=True), \
             patch("subprocess.run", return_value=_proc(returncode=0)):
            result = self.adapter.connect({"profile": "Home VPN"})
        assert result is True

    def test_connect_no_profile(self):
        result = self.adapter.connect({})
        assert result is False

    def test_connect_failure(self):
        with patch("os.path.isdir", return_value=True), \
             patch("subprocess.run", return_value=_proc(returncode=1)):
            result = self.adapter.connect({"profile": "Home VPN"})
        assert result is False

    def test_disconnect_success(self):
        with patch("subprocess.run", return_value=_proc(returncode=0)):
            assert self.adapter.disconnect() is True

    def test_disconnect_failure(self):
        with patch("subprocess.run", return_value=_proc(returncode=1)):
            assert self.adapter.disconnect() is False


# ---------------------------------------------------------------------------
# Replayer: app_open handler
# ---------------------------------------------------------------------------

class TestReplayerAppOpen:
    def _make_replayer(self, actions):
        from ctx.replayer.replayer import Replayer
        return Replayer("test-ws", actions)

    def test_app_open_launches_app(self, capsys):
        r = self._make_replayer([{"type": "app_open", "app_name": "Slack"}])
        with patch("subprocess.run", return_value=_proc(returncode=0)) as mock_run:
            r.replay()
        args = mock_run.call_args_list[0][0][0]
        assert args == ["open", "-a", "Slack"]

    def test_app_open_places_in_workspace(self, capsys):
        r = self._make_replayer([
            {"type": "app_open", "app_name": "Microsoft Teams", "workspace": "1"}
        ])
        mock_wm = MagicMock()
        mock_wm.move_app_to_workspace.return_value = True
        with patch("subprocess.run", return_value=_proc(returncode=0)), \
             patch("ctx.replayer.replayer.time") as mock_time, \
             patch("ctx.adapters.wm.registry.WorkspaceManagerRegistry") as mock_reg:
            mock_reg.return_value.detect_active.return_value = mock_wm
            r._aerospace = mock_wm
            r.replay()
        mock_wm.move_app_to_workspace.assert_called_once_with("Microsoft Teams", "1")

    def test_app_open_warn_on_failure(self, capsys):
        r = self._make_replayer([{"type": "app_open", "app_name": "NonExistentApp"}])
        with patch("subprocess.run", return_value=_proc(returncode=1)):
            r.replay()
        out = capsys.readouterr().out
        assert "warn" in out

    def test_app_open_no_workspace_no_placement(self):
        r = self._make_replayer([{"type": "app_open", "app_name": "Slack"}])
        with patch("subprocess.run", return_value=_proc(returncode=0)):
            with patch.object(r, "_place_in_workspace") as mock_place:
                r.replay()
        mock_place.assert_not_called()
