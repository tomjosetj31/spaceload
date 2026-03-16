"""Synchronous point-in-time environment capture.

Reads the current state of all adapters and returns a list of action dicts
in the same format as a saved workspace. No daemon required.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from spaceload.adapters.browser.registry import BrowserAdapterRegistry
from spaceload.adapters.ide.registry import IDEAdapterRegistry
from spaceload.adapters.terminal.registry import TerminalAdapterRegistry
from spaceload.adapters.vpn.registry import VPNAdapterRegistry

logger = logging.getLogger(__name__)


def capture_current() -> list[dict]:
    """Return a list of action dicts representing the current environment.

    Queries all available adapter registries synchronously. Errors in
    individual adapters are logged and skipped so a partial result is
    always returned.
    """

    actions: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    # --- Browser tabs ---
    browser_registry = BrowserAdapterRegistry()
    for adapter in browser_registry.available_adapters():
        try:
            for url in adapter.get_open_tabs():
                if url and url.strip():
                    actions.append({
                        "type": "browser_tab_open",
                        "browser": adapter.name,
                        "url": url.strip(),
                        "timestamp": now,
                    })
        except Exception as exc:
            logger.warning("capturer: browser %s failed: %s", adapter.name, exc)

    # --- IDE projects ---
    ide_registry = IDEAdapterRegistry()
    for adapter in ide_registry.available_adapters():
        try:
            for path in adapter.get_open_projects():
                if path and path.strip():
                    actions.append({
                        "type": "ide_project_open",
                        "client": adapter.name,
                        "path": path.strip(),
                        "timestamp": now,
                    })
        except Exception as exc:
            logger.warning("capturer: IDE %s failed: %s", adapter.name, exc)

    # --- Terminal sessions ---
    terminal_registry = TerminalAdapterRegistry()
    for adapter in terminal_registry.available_adapters():
        try:
            for session in adapter.get_sessions():
                actions.append({
                    "type": "terminal_session_open",
                    "app": session.app,
                    "directory": session.directory,
                    "session_id": session.session_id,
                    "timestamp": now,
                })
        except Exception as exc:
            logger.warning("capturer: terminal %s failed: %s", adapter.name, exc)

    # --- VPN ---
    vpn_registry = VPNAdapterRegistry()
    try:
        result = vpn_registry.detect_active()
        if result is not None:
            adapter, state = result
            actions.append({
                "type": "vpn_connect",
                "client": adapter.name,
                "profile": state.profile,
                "timestamp": now,
            })
    except Exception as exc:
        logger.warning("capturer: VPN detection failed: %s", exc)

    return actions
