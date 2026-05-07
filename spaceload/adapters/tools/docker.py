"""Docker tool adapter for spaceload."""

from __future__ import annotations

import logging
import shutil
import subprocess

from spaceload.adapters.tools.base import ToolAdapter

logger = logging.getLogger(__name__)


class DockerAdapter(ToolAdapter):
    """Adapter for Docker: records running containers and starts them on replay."""

    name = "docker"
    action_type = "docker_containers"

    def is_available(self) -> bool:
        """Return True if the docker binary is on PATH."""
        return shutil.which("docker") is not None

    def detect(self) -> dict | None:
        """Return the names of currently running containers, or None if unavailable."""
        if not self.is_available():
            return None
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.debug("DockerAdapter.detect(): docker ps failed (returncode=%d)", result.returncode)
                return None
            containers = [c.strip() for c in result.stdout.strip().splitlines() if c.strip()]
            return {"containers": containers}
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("DockerAdapter.detect() failed: %s", exc)
            return None

    def apply(self, state: dict) -> bool:
        """Start each recorded container with 'docker start <name>'.

        Returns True if all starts succeeded, False if any failed.
        """
        containers = state.get("containers", [])
        if not containers:
            return True
        all_ok = True
        for name in containers:
            try:
                result = subprocess.run(
                    ["docker", "start", name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    logger.warning(
                        "DockerAdapter.apply(): failed to start %r: %s",
                        name,
                        result.stderr.strip(),
                    )
                    all_ok = False
            except (subprocess.SubprocessError, OSError) as exc:
                logger.warning("DockerAdapter.apply(): error starting %r: %s", name, exc)
                all_ok = False
        return all_ok
