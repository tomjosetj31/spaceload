"""Cisco AnyConnect VPN adapter for ctx."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from loadout.adapters.vpn.base import VPNAdapter, VPNState, retry_connect

logger = logging.getLogger(__name__)

_CISCO_BINARY = "/opt/cisco/anyconnect/bin/vpn"


class CiscoAnyConnectAdapter(VPNAdapter):
    """VPN adapter for Cisco AnyConnect."""

    name = "cisco"

    def is_available(self) -> bool:
        """Return True if the Cisco AnyConnect binary exists at its fixed path."""
        return Path(_CISCO_BINARY).exists()

    def detect(self) -> Optional[VPNState]:
        """Run 'vpn status' and return VPNState based on output."""
        if not self.is_available():
            return None
        try:
            result = subprocess.run(
                [_CISCO_BINARY, "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout + result.stderr
            connected = "Connected" in output
            profile: Optional[str] = None
            for line in output.splitlines():
                line = line.strip()
                if line.lower().startswith("profile:"):
                    profile = line.split(":", 1)[1].strip()
                    break
            return VPNState(connected=connected, profile=profile, client="cisco")
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("CiscoAnyConnectAdapter.detect() failed: %s", exc)
            return VPNState(connected=False, client="cisco")

    def connect(self, config: dict) -> bool:
        """Run 'vpn connect <profile>' with retry logic. Returns True on success."""
        profile = config.get("profile", "")

        def _attempt() -> bool:
            try:
                cmd = [_CISCO_BINARY, "connect"]
                if profile:
                    cmd.append(profile)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                output = result.stdout + result.stderr
                return result.returncode == 0 or "Connected" in output
            except (subprocess.SubprocessError, OSError) as exc:
                logger.warning("CiscoAnyConnectAdapter.connect() attempt failed: %s", exc)
                return False

        success = retry_connect(_attempt)
        if not success:
            logger.warning("CiscoAnyConnectAdapter.connect() failed after all retries")
        return success

    def disconnect(self) -> bool:
        """Run 'vpn disconnect'. Returns True on success."""
        try:
            result = subprocess.run(
                [_CISCO_BINARY, "disconnect"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("CiscoAnyConnectAdapter.disconnect() failed: %s", exc)
            return False

    def get_config(self) -> dict:
        """Return current Cisco AnyConnect config snapshot for replay."""
        state = self.detect()
        profile = state.profile if state else None
        return {"client": "cisco", "profile": profile}
