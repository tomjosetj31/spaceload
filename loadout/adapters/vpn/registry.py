"""VPN adapter registry — auto-detects available VPN clients on this system."""

from __future__ import annotations

import logging
from typing import Optional

from loadout.adapters.vpn.base import VPNAdapter, VPNState
from loadout.adapters.vpn.tailscale import TailscaleAdapter
from loadout.adapters.vpn.wireguard import WireGuardAdapter
from loadout.adapters.vpn.cisco import CiscoAnyConnectAdapter
from loadout.adapters.vpn.mullvad import MullvadAdapter
from loadout.adapters.vpn.openvpn import OpenVPNAdapter
from loadout.adapters.vpn.tunnelblick import TunnelblickAdapter

logger = logging.getLogger(__name__)


class VPNAdapterRegistry:
    """Registry of all known VPN adapters.

    Provides methods to query which adapters are available on the current
    system and to detect which (if any) is actively connected.
    """

    def __init__(self) -> None:
        self._adapters: list[VPNAdapter] = [
            TailscaleAdapter(),
            WireGuardAdapter(),
            CiscoAnyConnectAdapter(),
            MullvadAdapter(),
            OpenVPNAdapter(),
            TunnelblickAdapter(),
        ]

    def available_adapters(self) -> list[VPNAdapter]:
        """Return adapters whose VPN client binary is present on this system."""
        return [a for a in self._adapters if a.is_available()]

    def detect_active(self) -> Optional[tuple[VPNAdapter, VPNState]]:
        """Return (adapter, state) for the first connected VPN, or None."""
        for adapter in self._adapters:
            try:
                state = adapter.detect()
            except Exception as exc:
                logger.warning(
                    "VPNAdapterRegistry: error detecting %s: %s", adapter.name, exc
                )
                continue
            if state is not None and state.connected:
                return (adapter, state)
        return None

    def get_adapter(self, name: str) -> Optional[VPNAdapter]:
        """Return adapter by name (e.g. 'tailscale'), or None if not found."""
        for adapter in self._adapters:
            if adapter.name == name:
                return adapter
        return None
