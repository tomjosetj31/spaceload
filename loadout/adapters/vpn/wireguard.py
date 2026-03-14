"""WireGuard VPN adapter for ctx."""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional

from loadout.adapters.vpn.base import VPNAdapter, VPNState, retry_connect

logger = logging.getLogger(__name__)


class WireGuardAdapter(VPNAdapter):
    """VPN adapter for WireGuard (wg / wg-quick)."""

    name = "wireguard"

    def is_available(self) -> bool:
        """Return True if both 'wg' and 'wg-quick' binaries are on PATH."""
        return shutil.which("wg") is not None and shutil.which("wg-quick") is not None

    def _get_active_interface(self) -> Optional[str]:
        """Return the first active WireGuard interface name, or None."""
        try:
            result = subprocess.run(
                ["wg", "show"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("interface:"):
                    return line.split(":", 1)[1].strip()
            return None
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("WireGuardAdapter._get_active_interface() failed: %s", exc)
            return None

    def detect(self) -> Optional[VPNState]:
        """Run 'wg show' and return VPNState based on active interfaces."""
        if not self.is_available():
            return None
        interface = self._get_active_interface()
        connected = interface is not None
        return VPNState(connected=connected, profile=interface, client="wireguard")

    def connect(self, config: dict) -> bool:
        """Run 'wg-quick up <interface>' with retry logic. Returns True on success."""
        interface = config.get("interface") or config.get("profile")
        if not interface:
            logger.warning("WireGuardAdapter.connect(): no interface specified in config")
            return False

        def _attempt() -> bool:
            try:
                result = subprocess.run(
                    ["wg-quick", "up", interface],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result.returncode == 0
            except (subprocess.SubprocessError, OSError) as exc:
                logger.warning("WireGuardAdapter.connect() attempt failed: %s", exc)
                return False

        success = retry_connect(_attempt)
        if not success:
            logger.warning("WireGuardAdapter.connect() failed after all retries")
        return success

    def disconnect(self) -> bool:
        """Run 'wg-quick down <interface>'. Returns True on success."""
        interface = self._get_active_interface()
        if not interface:
            logger.warning("WireGuardAdapter.disconnect(): no active interface found")
            return False
        try:
            result = subprocess.run(
                ["wg-quick", "down", interface],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("WireGuardAdapter.disconnect() failed: %s", exc)
            return False

    def get_config(self) -> dict:
        """Return current WireGuard config snapshot for replay."""
        interface = self._get_active_interface()
        return {"client": "wireguard", "interface": interface}
