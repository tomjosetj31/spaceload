"""VPN adapter base class and retry helper for ctx."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class VPNState:
    """Snapshot of a VPN connection state."""

    connected: bool
    profile: Optional[str] = None
    client: str = ""


class VPNAdapter(ABC):
    """Abstract base class for VPN adapters."""

    name: str = ""

    @abstractmethod
    def detect(self) -> Optional[VPNState]:
        """Return VPNState if this adapter's VPN client is installed/running, else None."""
        ...

    @abstractmethod
    def connect(self, config: dict) -> bool:
        """Attempt to connect using the given config. Returns True on success."""
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        """Disconnect the VPN. Returns True on success."""
        ...

    @abstractmethod
    def get_config(self) -> dict:
        """Return a snapshot of current config suitable for replay."""
        ...

    def is_available(self) -> bool:
        """Return True if the VPN client binary exists on this system."""
        return False


def retry_connect(fn, retries: int = 3, delay: float = 2.0) -> bool:
    """Call *fn* up to *retries* times, sleeping *delay* seconds between attempts.

    Returns True as soon as *fn* returns True, or False if all attempts fail.
    """
    for attempt in range(retries):
        if fn():
            return True
        if attempt < retries - 1:
            time.sleep(delay)
    return False
