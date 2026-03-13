"""Unit tests for VPN adapters (mocked subprocess calls)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ctx.adapters.vpn.base import VPNAdapter, VPNState, retry_connect
from ctx.adapters.vpn.tailscale import TailscaleAdapter
from ctx.adapters.vpn.wireguard import WireGuardAdapter
from ctx.adapters.vpn.cisco import CiscoAnyConnectAdapter
from ctx.adapters.vpn.mullvad import MullvadAdapter
from ctx.adapters.vpn.openvpn import OpenVPNAdapter
from ctx.adapters.vpn.registry import VPNAdapterRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completed_process(stdout="", stderr="", returncode=0):
    """Return a mock CompletedProcess-like object."""
    mock = MagicMock()
    mock.stdout = stdout
    mock.stderr = stderr
    mock.returncode = returncode
    return mock


# ---------------------------------------------------------------------------
# retry_connect
# ---------------------------------------------------------------------------

class TestRetryConnect:
    def test_succeeds_on_first_try(self):
        fn = MagicMock(return_value=True)
        assert retry_connect(fn, retries=3, delay=0) is True
        assert fn.call_count == 1

    def test_succeeds_on_second_try(self):
        fn = MagicMock(side_effect=[False, True])
        assert retry_connect(fn, retries=3, delay=0) is True
        assert fn.call_count == 2

    def test_fails_all_retries(self):
        fn = MagicMock(return_value=False)
        assert retry_connect(fn, retries=3, delay=0) is False
        assert fn.call_count == 3

    def test_respects_retry_count(self):
        fn = MagicMock(return_value=False)
        retry_connect(fn, retries=5, delay=0)
        assert fn.call_count == 5


# ---------------------------------------------------------------------------
# TailscaleAdapter
# ---------------------------------------------------------------------------

class TestTailscaleAdapter:
    def setup_method(self):
        self.adapter = TailscaleAdapter()

    def test_is_available_when_binary_exists(self):
        with patch("shutil.which", return_value="/usr/bin/tailscale"):
            assert self.adapter.is_available() is True

    def test_is_available_when_binary_missing(self):
        with patch("shutil.which", return_value=None):
            assert self.adapter.is_available() is False

    def test_detect_connected(self):
        status_json = json.dumps({
            "BackendState": "Running",
            "CurrentTailnet": {"Name": "mynet"},
        })
        with patch("shutil.which", return_value="/usr/bin/tailscale"), \
             patch("subprocess.run", return_value=_make_completed_process(stdout=status_json)):
            state = self.adapter.detect()
        assert state is not None
        assert state.connected is True
        assert state.client == "tailscale"
        assert state.profile == "mynet"

    def test_detect_not_connected(self):
        status_json = json.dumps({"BackendState": "Stopped"})
        with patch("shutil.which", return_value="/usr/bin/tailscale"), \
             patch("subprocess.run", return_value=_make_completed_process(stdout=status_json)):
            state = self.adapter.detect()
        assert state is not None
        assert state.connected is False

    def test_detect_returns_none_when_not_available(self):
        with patch("shutil.which", return_value=None):
            state = self.adapter.detect()
        assert state is None

    def test_connect_success(self):
        with patch("shutil.which", return_value="/usr/bin/tailscale"), \
             patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            result = self.adapter.connect({})
        assert result is True

    def test_connect_failure_returns_false(self):
        with patch("shutil.which", return_value="/usr/bin/tailscale"), \
             patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            # Patch time.sleep to skip delays
            with patch("ctx.adapters.vpn.base.time.sleep"):
                result = self.adapter.connect({})
        assert result is False

    def test_disconnect_success(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            result = self.adapter.disconnect()
        assert result is True

    def test_disconnect_failure(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            result = self.adapter.disconnect()
        assert result is False

    def test_get_config_structure(self):
        status_json = json.dumps({"BackendState": "Running"})
        with patch("subprocess.run", return_value=_make_completed_process(stdout=status_json)):
            config = self.adapter.get_config()
        assert config["client"] == "tailscale"
        assert "profile" in config


# ---------------------------------------------------------------------------
# WireGuardAdapter
# ---------------------------------------------------------------------------

class TestWireGuardAdapter:
    def setup_method(self):
        self.adapter = WireGuardAdapter()

    def test_is_available_when_both_binaries_exist(self):
        with patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"):
            assert self.adapter.is_available() is True

    def test_is_available_when_wg_missing(self):
        with patch("shutil.which", side_effect=lambda x: None if x == "wg" else f"/usr/bin/{x}"):
            assert self.adapter.is_available() is False

    def test_is_available_when_wg_quick_missing(self):
        with patch("shutil.which", side_effect=lambda x: None if x == "wg-quick" else f"/usr/bin/{x}"):
            assert self.adapter.is_available() is False

    def test_detect_connected(self):
        wg_output = "interface: wg0\n  public key: abc\n  listening port: 51820\n"
        with patch("shutil.which", return_value="/usr/bin/wg"), \
             patch("subprocess.run", return_value=_make_completed_process(stdout=wg_output)):
            state = self.adapter.detect()
        assert state is not None
        assert state.connected is True
        assert state.profile == "wg0"
        assert state.client == "wireguard"

    def test_detect_not_connected(self):
        with patch("shutil.which", return_value="/usr/bin/wg"), \
             patch("subprocess.run", return_value=_make_completed_process(stdout="", returncode=1)):
            state = self.adapter.detect()
        assert state is not None
        assert state.connected is False

    def test_detect_returns_none_when_not_available(self):
        with patch("shutil.which", return_value=None):
            state = self.adapter.detect()
        assert state is None

    def test_connect_success(self):
        with patch("shutil.which", return_value="/usr/bin/wg"), \
             patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            result = self.adapter.connect({"interface": "wg0"})
        assert result is True

    def test_connect_no_interface_returns_false(self):
        result = self.adapter.connect({})
        assert result is False

    def test_connect_failure_returns_false(self):
        with patch("shutil.which", return_value="/usr/bin/wg"), \
             patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            with patch("ctx.adapters.vpn.base.time.sleep"):
                result = self.adapter.connect({"interface": "wg0"})
        assert result is False

    def test_disconnect_success(self):
        wg_output = "interface: wg0\n"
        # First call is for _get_active_interface, second for wg-quick down
        with patch("subprocess.run", side_effect=[
            _make_completed_process(stdout=wg_output),
            _make_completed_process(returncode=0),
        ]):
            result = self.adapter.disconnect()
        assert result is True

    def test_disconnect_no_interface(self):
        with patch("subprocess.run", return_value=_make_completed_process(stdout="", returncode=1)):
            result = self.adapter.disconnect()
        assert result is False

    def test_get_config_structure(self):
        wg_output = "interface: wg0\n"
        with patch("subprocess.run", return_value=_make_completed_process(stdout=wg_output)):
            config = self.adapter.get_config()
        assert config["client"] == "wireguard"
        assert config["interface"] == "wg0"


# ---------------------------------------------------------------------------
# CiscoAnyConnectAdapter
# ---------------------------------------------------------------------------

class TestCiscoAnyConnectAdapter:
    def setup_method(self):
        self.adapter = CiscoAnyConnectAdapter()

    def test_is_available_when_binary_exists(self, tmp_path):
        with patch("ctx.adapters.vpn.cisco.Path") as mock_path_cls:
            mock_path_cls.return_value.exists.return_value = True
            assert self.adapter.is_available() is True

    def test_is_available_when_binary_missing(self):
        with patch("ctx.adapters.vpn.cisco.Path") as mock_path_cls:
            mock_path_cls.return_value.exists.return_value = False
            assert self.adapter.is_available() is False

    def test_detect_connected(self):
        vpn_output = "state: Connected\nprofile: work-vpn\n"
        with patch("ctx.adapters.vpn.cisco.Path") as mock_path_cls, \
             patch("subprocess.run", return_value=_make_completed_process(stdout=vpn_output)):
            mock_path_cls.return_value.exists.return_value = True
            state = self.adapter.detect()
        assert state is not None
        assert state.connected is True
        assert state.client == "cisco"

    def test_detect_not_connected(self):
        vpn_output = "state: Disconnected\n"
        with patch("ctx.adapters.vpn.cisco.Path") as mock_path_cls, \
             patch("subprocess.run", return_value=_make_completed_process(stdout=vpn_output)):
            mock_path_cls.return_value.exists.return_value = True
            state = self.adapter.detect()
        assert state is not None
        assert state.connected is False

    def test_detect_returns_none_when_not_available(self):
        with patch("ctx.adapters.vpn.cisco.Path") as mock_path_cls:
            mock_path_cls.return_value.exists.return_value = False
            state = self.adapter.detect()
        assert state is None

    def test_connect_success(self):
        with patch("ctx.adapters.vpn.cisco.Path") as mock_path_cls, \
             patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            mock_path_cls.return_value.exists.return_value = True
            result = self.adapter.connect({"profile": "work"})
        assert result is True

    def test_connect_failure_returns_false(self):
        with patch("ctx.adapters.vpn.cisco.Path") as mock_path_cls, \
             patch("subprocess.run", return_value=_make_completed_process(returncode=1, stdout="Error")):
            mock_path_cls.return_value.exists.return_value = True
            with patch("ctx.adapters.vpn.base.time.sleep"):
                result = self.adapter.connect({"profile": "work"})
        assert result is False

    def test_disconnect_success(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            result = self.adapter.disconnect()
        assert result is True

    def test_get_config_structure(self):
        with patch.object(self.adapter, "detect", return_value=VPNState(connected=True, profile="work", client="cisco")):
            config = self.adapter.get_config()
        assert config["client"] == "cisco"
        assert config["profile"] == "work"


# ---------------------------------------------------------------------------
# MullvadAdapter
# ---------------------------------------------------------------------------

class TestMullvadAdapter:
    def setup_method(self):
        self.adapter = MullvadAdapter()

    def test_is_available_when_binary_exists(self):
        with patch("shutil.which", return_value="/usr/bin/mullvad"):
            assert self.adapter.is_available() is True

    def test_is_available_when_binary_missing(self):
        with patch("shutil.which", return_value=None):
            assert self.adapter.is_available() is False

    def test_detect_connected(self):
        output = "Connected to se-got-wg-001 in Gothenburg, SE\n"
        with patch("shutil.which", return_value="/usr/bin/mullvad"), \
             patch("subprocess.run", return_value=_make_completed_process(stdout=output)):
            state = self.adapter.detect()
        assert state is not None
        assert state.connected is True
        assert state.client == "mullvad"
        assert state.profile == "se-got-wg-001"

    def test_detect_not_connected(self):
        output = "Disconnected\n"
        with patch("shutil.which", return_value="/usr/bin/mullvad"), \
             patch("subprocess.run", return_value=_make_completed_process(stdout=output)):
            state = self.adapter.detect()
        assert state is not None
        assert state.connected is False

    def test_detect_returns_none_when_not_available(self):
        with patch("shutil.which", return_value=None):
            state = self.adapter.detect()
        assert state is None

    def test_connect_success(self):
        with patch("shutil.which", return_value="/usr/bin/mullvad"), \
             patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            result = self.adapter.connect({})
        assert result is True

    def test_connect_failure_returns_false(self):
        with patch("shutil.which", return_value="/usr/bin/mullvad"), \
             patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            with patch("ctx.adapters.vpn.base.time.sleep"):
                result = self.adapter.connect({})
        assert result is False

    def test_disconnect_success(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            result = self.adapter.disconnect()
        assert result is True

    def test_disconnect_failure(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            result = self.adapter.disconnect()
        assert result is False

    def test_get_config_structure(self):
        with patch.object(self.adapter, "detect", return_value=VPNState(connected=True, profile="se-got-wg-001", client="mullvad")):
            config = self.adapter.get_config()
        assert config["client"] == "mullvad"
        assert config["profile"] == "se-got-wg-001"


# ---------------------------------------------------------------------------
# OpenVPNAdapter
# ---------------------------------------------------------------------------

class TestOpenVPNAdapter:
    def setup_method(self):
        self.adapter = OpenVPNAdapter()

    def test_is_available_when_binary_exists(self):
        with patch("shutil.which", return_value="/usr/sbin/openvpn"):
            assert self.adapter.is_available() is True

    def test_is_available_when_binary_missing(self):
        with patch("shutil.which", return_value=None):
            assert self.adapter.is_available() is False

    def test_detect_connected(self):
        with patch("shutil.which", return_value="/usr/sbin/openvpn"), \
             patch("subprocess.run", return_value=_make_completed_process(stdout="1234", returncode=0)):
            state = self.adapter.detect()
        assert state is not None
        assert state.connected is True
        assert state.client == "openvpn"

    def test_detect_not_connected(self):
        with patch("shutil.which", return_value="/usr/sbin/openvpn"), \
             patch("subprocess.run", return_value=_make_completed_process(stdout="", returncode=1)):
            state = self.adapter.detect()
        assert state is not None
        assert state.connected is False

    def test_detect_returns_none_when_not_available(self):
        with patch("shutil.which", return_value=None):
            state = self.adapter.detect()
        assert state is None

    def test_connect_success(self):
        with patch("shutil.which", return_value="/usr/sbin/openvpn"), \
             patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            result = self.adapter.connect({"config_file": "/etc/openvpn/client.conf"})
        assert result is True

    def test_connect_no_config_returns_false(self):
        result = self.adapter.connect({})
        assert result is False

    def test_connect_failure_returns_false(self):
        with patch("shutil.which", return_value="/usr/sbin/openvpn"), \
             patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            with patch("ctx.adapters.vpn.base.time.sleep"):
                result = self.adapter.connect({"config_file": "/etc/openvpn/client.conf"})
        assert result is False

    def test_disconnect_success(self):
        # First call: pgrep returns pid; second call: kill succeeds
        with patch("subprocess.run", side_effect=[
            _make_completed_process(stdout="5678", returncode=0),
            _make_completed_process(returncode=0),
        ]):
            result = self.adapter.disconnect()
        assert result is True

    def test_disconnect_no_process(self):
        with patch("subprocess.run", return_value=_make_completed_process(stdout="", returncode=1)):
            result = self.adapter.disconnect()
        assert result is False

    def test_get_config_structure(self):
        with patch("subprocess.run", return_value=_make_completed_process(stdout="5678", returncode=0)):
            config = self.adapter.get_config()
        assert config["client"] == "openvpn"
        assert "pid" in config


# ---------------------------------------------------------------------------
# VPNAdapterRegistry
# ---------------------------------------------------------------------------

class TestVPNAdapterRegistry:
    def setup_method(self):
        self.registry = VPNAdapterRegistry()

    def test_available_adapters_returns_subset(self):
        # Make only tailscale available
        for adapter in self.registry._adapters:
            if adapter.name == "tailscale":
                adapter.is_available = lambda: True
            else:
                adapter.is_available = lambda: False

        available = self.registry.available_adapters()
        assert len(available) == 1
        assert available[0].name == "tailscale"

    def test_available_adapters_empty_when_none_available(self):
        for adapter in self.registry._adapters:
            adapter.is_available = lambda: False
        assert self.registry.available_adapters() == []

    def test_detect_active_returns_first_connected(self):
        # Make all return not connected except wireguard
        for adapter in self.registry._adapters:
            if adapter.name == "wireguard":
                adapter.detect = lambda: VPNState(connected=True, profile="wg0", client="wireguard")
            else:
                adapter.detect = lambda: VPNState(connected=False, client="other")

        result = self.registry.detect_active()
        # tailscale is first in the list; wireguard is second
        # tailscale returns connected=False, wireguard returns connected=True
        assert result is not None
        adapter, state = result
        assert adapter.name == "wireguard"
        assert state.connected is True

    def test_detect_active_returns_none_when_all_disconnected(self):
        for adapter in self.registry._adapters:
            adapter.detect = lambda: VPNState(connected=False, client="x")
        result = self.registry.detect_active()
        assert result is None

    def test_detect_active_skips_none_detect_results(self):
        for adapter in self.registry._adapters:
            adapter.detect = lambda: None
        result = self.registry.detect_active()
        assert result is None

    def test_get_adapter_by_name(self):
        adapter = self.registry.get_adapter("tailscale")
        assert adapter is not None
        assert adapter.name == "tailscale"

    def test_get_adapter_by_name_mullvad(self):
        adapter = self.registry.get_adapter("mullvad")
        assert adapter is not None
        assert adapter.name == "mullvad"

    def test_get_adapter_unknown_name_returns_none(self):
        adapter = self.registry.get_adapter("nonexistent-vpn")
        assert adapter is None

    def test_all_adapter_names_are_registered(self):
        names = {a.name for a in self.registry._adapters}
        assert "tailscale" in names
        assert "wireguard" in names
        assert "cisco" in names
        assert "mullvad" in names
        assert "openvpn" in names
