"""OpenVPN adapter for ctx."""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional

from loadout.adapters.vpn.base import VPNAdapter, VPNState, retry_connect

logger = logging.getLogger(__name__)


class OpenVPNAdapter(VPNAdapter):
    """VPN adapter for OpenVPN."""

    name = "openvpn"

    def is_available(self) -> bool:
        """Return True if the openvpn binary is on PATH."""
        return shutil.which("openvpn") is not None

    def _get_openvpn_pid(self) -> Optional[int]:
        """Return the PID of the running openvpn process, or None."""
        try:
            result = subprocess.run(
                ["pgrep", "openvpn"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().splitlines()[0])
            return None
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            logger.warning("OpenVPNAdapter._get_openvpn_pid() failed: %s", exc)
            return None

    def detect(self) -> Optional[VPNState]:
        """Check if an openvpn process is running and return VPNState."""
        if not self.is_available():
            return None
        pid = self._get_openvpn_pid()
        connected = pid is not None
        return VPNState(connected=connected, profile=None, client="openvpn")

    def connect(self, config: dict) -> bool:
        """Run 'openvpn --config <config_file> --daemon' with retry logic."""
        config_file = config.get("config_file") or config.get("profile")
        if not config_file:
            logger.warning("OpenVPNAdapter.connect(): no config_file specified in config")
            return False

        def _attempt() -> bool:
            try:
                result = subprocess.run(
                    ["openvpn", "--config", config_file, "--daemon"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result.returncode == 0
            except (subprocess.SubprocessError, OSError) as exc:
                logger.warning("OpenVPNAdapter.connect() attempt failed: %s", exc)
                return False

        success = retry_connect(_attempt)
        if not success:
            logger.warning("OpenVPNAdapter.connect() failed after all retries")
        return success

    def disconnect(self) -> bool:
        """Kill the running openvpn process. Returns True on success."""
        pid = self._get_openvpn_pid()
        if pid is None:
            logger.warning("OpenVPNAdapter.disconnect(): no running openvpn process found")
            return False
        try:
            result = subprocess.run(
                ["kill", str(pid)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("OpenVPNAdapter.disconnect() failed: %s", exc)
            return False

    def get_config(self) -> dict:
        """Return current OpenVPN config snapshot for replay."""
        pid = self._get_openvpn_pid()
        return {"client": "openvpn", "pid": pid}
