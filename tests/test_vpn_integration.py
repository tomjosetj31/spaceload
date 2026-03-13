"""Integration tests for VPN poller and replayer VPN action handling."""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ctx.adapters.vpn.base import VPNState
from ctx.daemon.server import VPNPoller
from ctx.replayer.replayer import Replayer


# ---------------------------------------------------------------------------
# VPNPoller integration tests
# ---------------------------------------------------------------------------

class TestVPNPollerIntegration:
    """Test that VPNPoller correctly detects state changes and appends to action log."""

    def _make_registry(self, connected: bool, client: str = "tailscale", profile: str = "mynet"):
        """Return a mock VPNAdapterRegistry."""
        registry = MagicMock()
        if connected:
            mock_adapter = MagicMock()
            mock_adapter.name = client
            state = VPNState(connected=True, profile=profile, client=client)
            registry.detect_active.return_value = (mock_adapter, state)
        else:
            registry.detect_active.return_value = None
        return registry

    def test_vpn_connect_event_appended_on_transition(self):
        """Poller should emit vpn_connect when VPN goes from disconnected to connected."""
        actions: list[dict] = []
        poller = VPNPoller(actions, poll_interval=0.05)

        # Sequence: first poll (baseline = not connected), second poll (connected)
        call_count = 0

        def fake_detect_active():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # First poll: baseline, no event
            else:
                mock_adapter = MagicMock()
                mock_adapter.name = "tailscale"
                state = VPNState(connected=True, profile="mynet", client="tailscale")
                return (mock_adapter, state)

        mock_registry = MagicMock()
        mock_registry.detect_active.side_effect = fake_detect_active

        with patch("ctx.daemon.server.VPNAdapterRegistry", return_value=mock_registry):
            poller.start()
            # Wait long enough for at least 2 poll cycles
            time.sleep(0.3)
            poller.stop()

        # Should have one vpn_connect action
        vpn_connect_actions = [a for a in actions if a.get("type") == "vpn_connect"]
        assert len(vpn_connect_actions) >= 1
        action = vpn_connect_actions[0]
        assert action["client"] == "tailscale"
        assert action["profile"] == "mynet"
        assert "timestamp" in action

    def test_vpn_disconnect_event_appended_on_transition(self):
        """Poller should emit vpn_disconnect when VPN goes from connected to disconnected."""
        actions: list[dict] = []
        poller = VPNPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_detect_active():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First poll: baseline = connected
                mock_adapter = MagicMock()
                mock_adapter.name = "tailscale"
                state = VPNState(connected=True, profile="mynet", client="tailscale")
                return (mock_adapter, state)
            else:
                # Subsequent: disconnected
                return None

        mock_registry = MagicMock()
        mock_registry.detect_active.side_effect = fake_detect_active

        with patch("ctx.daemon.server.VPNAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        vpn_disconnect_actions = [a for a in actions if a.get("type") == "vpn_disconnect"]
        assert len(vpn_disconnect_actions) >= 1
        action = vpn_disconnect_actions[0]
        assert action["client"] == "tailscale"
        assert "timestamp" in action

    def test_no_event_when_state_stable_connected(self):
        """No events should be emitted when VPN stays connected throughout."""
        actions: list[dict] = []
        poller = VPNPoller(actions, poll_interval=0.05)

        mock_adapter = MagicMock()
        mock_adapter.name = "mullvad"
        state = VPNState(connected=True, profile="se-001", client="mullvad")
        mock_registry = MagicMock()
        mock_registry.detect_active.return_value = (mock_adapter, state)

        with patch("ctx.daemon.server.VPNAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        # All polls see the same connected state — only baseline set on first poll, no events
        assert actions == []

    def test_no_event_when_state_stable_disconnected(self):
        """No events should be emitted when VPN stays disconnected throughout."""
        actions: list[dict] = []
        poller = VPNPoller(actions, poll_interval=0.05)

        mock_registry = MagicMock()
        mock_registry.detect_active.return_value = None

        with patch("ctx.daemon.server.VPNAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        assert actions == []

    def test_action_log_contains_correct_vpn_connect_fields(self):
        """vpn_connect action must contain type, client, profile, timestamp."""
        actions: list[dict] = []
        poller = VPNPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_detect_active():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None
            mock_adapter = MagicMock()
            mock_adapter.name = "wireguard"
            state = VPNState(connected=True, profile="wg0", client="wireguard")
            return (mock_adapter, state)

        mock_registry = MagicMock()
        mock_registry.detect_active.side_effect = fake_detect_active

        with patch("ctx.daemon.server.VPNAdapterRegistry", return_value=mock_registry):
            poller.start()
            time.sleep(0.3)
            poller.stop()

        connect_actions = [a for a in actions if a.get("type") == "vpn_connect"]
        assert connect_actions, "Expected at least one vpn_connect action"
        action = connect_actions[0]
        assert action["type"] == "vpn_connect"
        assert action["client"] == "wireguard"
        assert action["profile"] == "wg0"
        assert isinstance(action["timestamp"], str)
        assert len(action["timestamp"]) > 0


# ---------------------------------------------------------------------------
# Replayer VPN action integration tests
# ---------------------------------------------------------------------------

class TestReplayerVPNActions:
    """Test that Replayer correctly handles vpn_connect and vpn_disconnect actions."""

    def _make_mock_registry(self, connect_result=True, disconnect_result=True):
        """Return a mock registry with a controllable adapter."""
        mock_adapter = MagicMock()
        mock_adapter.name = "tailscale"
        mock_adapter.connect.return_value = connect_result
        mock_adapter.disconnect.return_value = disconnect_result

        mock_registry = MagicMock()
        mock_registry.get_adapter.return_value = mock_adapter
        return mock_registry, mock_adapter

    def test_replay_vpn_connect_action(self, capsys):
        """Replayer should call adapter.connect() for vpn_connect actions."""
        mock_registry, mock_adapter = self._make_mock_registry(connect_result=True)

        actions = [
            {
                "type": "vpn_connect",
                "client": "tailscale",
                "profile": "mynet",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test-workspace", actions)
        replayer._registry = mock_registry

        replayer.replay()

        mock_registry.get_adapter.assert_called_once_with("tailscale")
        mock_adapter.connect.assert_called_once()

    def test_replay_vpn_disconnect_action(self, capsys):
        """Replayer should call adapter.disconnect() for vpn_disconnect actions."""
        mock_registry, mock_adapter = self._make_mock_registry(disconnect_result=True)

        actions = [
            {
                "type": "vpn_disconnect",
                "client": "tailscale",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test-workspace", actions)
        replayer._registry = mock_registry

        replayer.replay()

        mock_registry.get_adapter.assert_called_once_with("tailscale")
        mock_adapter.disconnect.assert_called_once()

    def test_replay_vpn_connect_failure_logs_warning(self, capsys):
        """Replayer should log a warning when vpn_connect fails after retries."""
        mock_registry, mock_adapter = self._make_mock_registry(connect_result=False)

        actions = [
            {
                "type": "vpn_connect",
                "client": "tailscale",
                "profile": "mynet",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test-workspace", actions)
        replayer._registry = mock_registry

        with patch("ctx.replayer.replayer.time.sleep"):
            replayer.replay()

        captured = capsys.readouterr()
        assert "warn" in captured.out.lower() or "failed" in captured.out.lower()

    def test_replay_vpn_connect_unknown_client_skips(self, capsys):
        """Replayer should gracefully skip vpn_connect if adapter not found."""
        mock_registry = MagicMock()
        mock_registry.get_adapter.return_value = None

        actions = [
            {
                "type": "vpn_connect",
                "client": "unknown-vpn",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test-workspace", actions)
        replayer._registry = mock_registry

        # Should not raise
        replayer.replay()

        captured = capsys.readouterr()
        assert "skip" in captured.out.lower() or "warn" in captured.out.lower()

    def test_replay_vpn_disconnect_unknown_client_skips(self, capsys):
        """Replayer should gracefully skip vpn_disconnect if adapter not found."""
        mock_registry = MagicMock()
        mock_registry.get_adapter.return_value = None

        actions = [
            {
                "type": "vpn_disconnect",
                "client": "unknown-vpn",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
        replayer = Replayer("test-workspace", actions)
        replayer._registry = mock_registry

        replayer.replay()

        captured = capsys.readouterr()
        assert "skip" in captured.out.lower() or "warn" in captured.out.lower()

    def test_replay_mixed_actions(self, capsys):
        """Replayer handles a mix of vpn and non-vpn actions correctly."""
        mock_registry, mock_adapter = self._make_mock_registry(connect_result=True)

        actions = [
            {
                "type": "open_tab",
                "data": {"url": "https://github.com"},
                "timestamp": "2026-01-01T00:00:00+00:00",
            },
            {
                "type": "vpn_connect",
                "client": "tailscale",
                "profile": "mynet",
                "timestamp": "2026-01-01T00:00:01+00:00",
            },
            {
                "type": "open_tab",
                "data": {"url": "https://internal.corp.com"},
                "timestamp": "2026-01-01T00:00:02+00:00",
            },
            {
                "type": "vpn_disconnect",
                "client": "tailscale",
                "timestamp": "2026-01-01T00:00:03+00:00",
            },
        ]
        replayer = Replayer("test-workspace", actions)
        replayer._registry = mock_registry

        replayer.replay()

        # connect and disconnect should each have been called once
        mock_adapter.connect.assert_called_once()
        mock_adapter.disconnect.assert_called_once()
        captured = capsys.readouterr()
        assert "open_tab" in captured.out
