"""Tool adapter base class for spaceload."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ToolAdapter(ABC):
    """Abstract base class for developer tool adapters.

    Each adapter captures state from a CLI tool or app and can restore it
    during replay.  ``detect()`` returns a payload dict (merged with ``type``
    and ``timestamp`` by the poller) or ``None`` when nothing can be read.
    ``apply()`` is called by the replayer with the full action dict.
    """

    name: str = ""
    action_type: str = ""  # e.g. "docker_containers", "kubectl_context"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the tool binary or config is present on this system."""

    @abstractmethod
    def detect(self) -> dict | None:
        """Return a state payload dict, or None if unavailable / no state."""

    @abstractmethod
    def apply(self, state: dict) -> bool:
        """Restore recorded state. Returns True on success."""
