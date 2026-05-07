"""Tool adapter registry for spaceload."""

from __future__ import annotations

import logging

from spaceload.adapters.tools.base import ToolAdapter
from spaceload.adapters.tools.docker import DockerAdapter
from spaceload.adapters.tools.kubectl import KubectlAdapter
from spaceload.adapters.tools.aws import AWSAdapter
from spaceload.adapters.tools.obsidian import ObsidianAdapter
from spaceload.adapters.tools.tableplus import TablePlusAdapter

logger = logging.getLogger(__name__)


class ToolAdapterRegistry:
    """Registry of all known developer tool adapters."""

    def __init__(self) -> None:
        self._adapters: list[ToolAdapter] = [
            DockerAdapter(),
            KubectlAdapter(),
            AWSAdapter(),
            ObsidianAdapter(),
            TablePlusAdapter(),
        ]

    def available_adapters(self) -> list[ToolAdapter]:
        """Return adapters whose tool is installed/accessible on this system."""
        return [a for a in self._adapters if a.is_available()]

    def get_adapter(self, name: str) -> ToolAdapter | None:
        """Return adapter by name (e.g. 'docker'), or None if not found."""
        for adapter in self._adapters:
            if adapter.name == name:
                return adapter
        return None
