"""VPN adapters for ctx."""

from loadout.adapters.vpn.base import VPNAdapter, VPNState, retry_connect
from loadout.adapters.vpn.registry import VPNAdapterRegistry

__all__ = ["VPNAdapter", "VPNState", "retry_connect", "VPNAdapterRegistry"]
