"""Tailscale VPN adapter for ctx."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Optional

from ctx.adapters.vpn.base import VPNAdapter, VPNState, retry_connect

logger = logging.getLogger(__name__)


class TailscaleAdapter(VPNAdapter):
    """VPN adapter for Tailscale."""

    name = "tailscale"

    def is_available(self) -> bool:
        """Return True if the tailscale binary is on PATH."""
        return shutil.which("tailscale") is not None

    def detect(self) -> Optional[VPNState]:
        """Run 'tailscale status --json' and return VPNState, or None if not available."""
        if not self.is_available():
            return None
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            data = json.loads(result.stdout)
            backend_state = data.get("BackendState", "")
            connected = backend_state == "Running"
            profile = data.get("CurrentTailnet", {}).get("Name") if isinstance(data.get("CurrentTailnet"), dict) else None
            return VPNState(connected=connected, profile=profile, client="tailscale")
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
            logger.warning("TailscaleAdapter.detect() failed: %s", exc)
            return VPNState(connected=False, client="tailscale")

    def connect(self, config: dict) -> bool:
        """Run 'tailscale up' with retry logic. Returns True on success."""
        def _attempt() -> bool:
            try:
                result = subprocess.run(
                    ["tailscale", "up"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result.returncode == 0
            except (subprocess.SubprocessError, OSError) as exc:
                logger.warning("TailscaleAdapter.connect() attempt failed: %s", exc)
                return False

        success = retry_connect(_attempt)
        if not success:
            logger.warning("TailscaleAdapter.connect() failed after all retries")
        return success

    def disconnect(self) -> bool:
        """Run 'tailscale down'. Returns True on success."""
        try:
            result = subprocess.run(
                ["tailscale", "down"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("TailscaleAdapter.disconnect() failed: %s", exc)
            return False

    def get_config(self) -> dict:
        """Return current Tailscale config snapshot for replay."""
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            profile = json.loads(result.stdout) if result.returncode == 0 else {}
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            profile = {}
        return {"client": "tailscale", "profile": profile}
