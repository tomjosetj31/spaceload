"""Tunnelblick VPN adapter for ctx."""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Optional

from loadout.adapters.vpn.base import VPNAdapter, VPNState

logger = logging.getLogger(__name__)

_TUNNELBLICK_APP = "/Applications/Tunnelblick.app"


def _applescript(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )


class TunnelblickAdapter(VPNAdapter):
    """VPN adapter for Tunnelblick (AppleScript-based)."""

    name = "tunnelblick"

    def is_available(self) -> bool:
        return os.path.isdir(_TUNNELBLICK_APP)

    def detect(self) -> Optional[VPNState]:
        if not self.is_available():
            return None
        try:
            # Get names of all configurations
            result = _applescript(
                'tell application "Tunnelblick" to return name of every configuration'
            )
            if result.returncode != 0:
                return VPNState(connected=False, client="tunnelblick")

            names_raw = result.stdout.strip()
            if not names_raw:
                return VPNState(connected=False, client="tunnelblick")

            # names come back as comma-separated: "Home VPN, Work VPN"
            names = [n.strip() for n in names_raw.split(",")]

            for name in names:
                state_result = _applescript(
                    f'tell application "Tunnelblick" to return state of first configuration'
                    f' whose name = "{name}"'
                )
                if state_result.returncode == 0:
                    state_str = state_result.stdout.strip().upper()
                    if state_str == "CONNECTED":
                        return VPNState(connected=True, profile=name, client="tunnelblick")

            return VPNState(connected=False, client="tunnelblick")
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("TunnelblickAdapter.detect() failed: %s", exc)
            return VPNState(connected=False, client="tunnelblick")

    def connect(self, config: dict) -> bool:
        profile = config.get("profile", "")
        if not profile:
            logger.warning("TunnelblickAdapter.connect(): no profile specified")
            return False
        try:
            result = _applescript(
                f'tell application "Tunnelblick" to connect "{profile}"'
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("TunnelblickAdapter.connect() failed: %s", exc)
            return False

    def disconnect(self) -> bool:
        try:
            result = _applescript(
                'tell application "Tunnelblick" to disconnectAll'
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("TunnelblickAdapter.disconnect() failed: %s", exc)
            return False

    def get_config(self) -> dict:
        state = self.detect()
        return {
            "client": "tunnelblick",
            "profile": state.profile if state and state.connected else None,
        }
