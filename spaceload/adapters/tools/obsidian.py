"""Obsidian adapter for spaceload."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from spaceload.adapters.tools.base import ToolAdapter

logger = logging.getLogger(__name__)

# Primary location on macOS
_CONFIG_PATH_MAC = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
# XDG fallback (Linux / custom setups)
_CONFIG_PATH_XDG = Path.home() / ".config" / "obsidian" / "obsidian.json"


def _config_path() -> Path | None:
    for p in (_CONFIG_PATH_MAC, _CONFIG_PATH_XDG):
        if p.exists():
            return p
    return None


class ObsidianAdapter(ToolAdapter):
    """Adapter for Obsidian: records the open vault path and reopens it on replay."""

    name = "obsidian"
    action_type = "obsidian_vault_open"

    def is_available(self) -> bool:
        """Return True if the Obsidian config file is present."""
        return _config_path() is not None

    def detect(self) -> dict | None:
        """Return the currently open vault path from obsidian.json, or None.

        Prefers the vault marked ``open: true``; falls back to the vault with
        the highest ``ts`` (most recently accessed).
        """
        cfg = _config_path()
        if cfg is None:
            return None
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("ObsidianAdapter.detect(): failed to read config: %s", exc)
            return None

        vaults = data.get("vaults", {})
        if not vaults:
            return None

        # Prefer the currently open vault
        open_vault = next(
            (v for v in vaults.values() if v.get("open")),
            None,
        )
        if open_vault:
            vault_path = open_vault.get("path", "")
            if vault_path:
                return {"vault_path": vault_path}

        # Fall back to most recently accessed vault
        most_recent = max(vaults.values(), key=lambda v: v.get("ts", 0), default=None)
        if most_recent:
            vault_path = most_recent.get("path", "")
            if vault_path:
                return {"vault_path": vault_path}

        return None

    def apply(self, state: dict) -> bool:
        """Open the recorded vault in Obsidian."""
        vault_path = state.get("vault_path", "")
        if not vault_path:
            return False
        try:
            result = subprocess.run(
                ["open", "-a", "Obsidian", vault_path],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning(
                    "ObsidianAdapter.apply(): failed to open vault %r", vault_path
                )
                return False
            return True
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("ObsidianAdapter.apply() failed: %s", exc)
            return False
