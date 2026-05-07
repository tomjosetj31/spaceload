"""kubectl tool adapter for spaceload."""

from __future__ import annotations

import logging
import shutil
import subprocess

from spaceload.adapters.tools.base import ToolAdapter

logger = logging.getLogger(__name__)


class KubectlAdapter(ToolAdapter):
    """Adapter for kubectl: records the active context and restores it on replay."""

    name = "kubectl"
    action_type = "kubectl_context"

    def is_available(self) -> bool:
        """Return True if kubectl is on PATH."""
        return shutil.which("kubectl") is not None

    def detect(self) -> dict | None:
        """Return the current kubectl context, or None if unavailable."""
        if not self.is_available():
            return None
        try:
            result = subprocess.run(
                ["kubectl", "config", "current-context"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.debug(
                    "KubectlAdapter.detect(): current-context failed (returncode=%d)",
                    result.returncode,
                )
                return None
            context = result.stdout.strip()
            if not context:
                return None
            return {"context": context}
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("KubectlAdapter.detect() failed: %s", exc)
            return None

    def apply(self, state: dict) -> bool:
        """Switch to the recorded kubectl context."""
        context = state.get("context", "")
        if not context:
            return False
        try:
            result = subprocess.run(
                ["kubectl", "config", "use-context", context],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                logger.warning(
                    "KubectlAdapter.apply(): use-context %r failed: %s",
                    context,
                    result.stderr.strip(),
                )
                return False
            return True
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("KubectlAdapter.apply() failed: %s", exc)
            return False
