"""Mullvad VPN adapter for ctx."""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional

from loadout.adapters.vpn.base import VPNAdapter, VPNState, retry_connect

logger = logging.getLogger(__name__)


class MullvadAdapter(VPNAdapter):
    """VPN adapter for Mullvad VPN."""

    name = "mullvad"

    def is_available(self) -> bool:
        """Return True if the mullvad binary is on PATH."""
        return shutil.which("mullvad") is not None

    def detect(self) -> Optional[VPNState]:
        """Run 'mullvad status' and return VPNState based on output."""
        if not self.is_available():
            return None
        try:
            result = subprocess.run(
                ["mullvad", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout + result.stderr
            connected = "Connected" in output
            profile: Optional[str] = None
            for line in output.splitlines():
                line = line.strip()
                if "Connected to" in line:
                    # e.g. "Connected to se-got-wg-001 in Gothenburg, SE"
                    parts = line.split("Connected to", 1)
                    if len(parts) > 1:
                        profile = parts[1].strip().split()[0] if parts[1].strip() else None
                    break
            return VPNState(connected=connected, profile=profile, client="mullvad")
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("MullvadAdapter.detect() failed: %s", exc)
            return VPNState(connected=False, client="mullvad")

    def connect(self, config: dict) -> bool:
        """Run 'mullvad connect' with retry logic. Returns True on success."""
        def _attempt() -> bool:
            try:
                result = subprocess.run(
                    ["mullvad", "connect"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result.returncode == 0
            except (subprocess.SubprocessError, OSError) as exc:
                logger.warning("MullvadAdapter.connect() attempt failed: %s", exc)
                return False

        success = retry_connect(_attempt)
        if not success:
            logger.warning("MullvadAdapter.connect() failed after all retries")
        return success

    def disconnect(self) -> bool:
        """Run 'mullvad disconnect'. Returns True on success."""
        try:
            result = subprocess.run(
                ["mullvad", "disconnect"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("MullvadAdapter.disconnect() failed: %s", exc)
            return False

    def get_config(self) -> dict:
        """Return current Mullvad config snapshot for replay."""
        state = self.detect()
        profile = state.profile if state else None
        return {"client": "mullvad", "profile": profile}
