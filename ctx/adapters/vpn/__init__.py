"""VPN adapters for ctx."""

from ctx.adapters.vpn.base import VPNAdapter, VPNState, retry_connect
from ctx.adapters.vpn.registry import VPNAdapterRegistry

__all__ = ["VPNAdapter", "VPNState", "retry_connect", "VPNAdapterRegistry"]
