"""Workspace replayer — executes recorded action sequences.

Phase 1: stub implementation that prints actions without executing them.
Phase 2: adds VPN connect/disconnect replay via the VPN adapter registry.
Phase 3: adds browser tab replay via the browser adapter registry.
Phase 4: adds IDE project replay via the IDE adapter registry.
Phase 5: adds terminal session replay via the terminal adapter registry.
Phase 6: AeroSpace workspace placement — after opening each app, moves its
         window to the recorded AeroSpace workspace.
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

_SENTINEL = object()  # marks "not yet initialised" for the aerospace field

# How long to wait (seconds) after opening an app before trying to move its window
_AEROSPACE_SETTLE = 1.5


def _retry_vpn_action(fn, retries: int = 3, delay: float = 2.0) -> bool:
    """Call *fn* up to *retries* times with *delay* seconds between attempts.

    Returns True if any attempt succeeds, False otherwise.
    """
    for attempt in range(retries):
        if fn():
            return True
        if attempt < retries - 1:
            time.sleep(delay)
    return False


class Replayer:
    """Replays a list of workspace actions."""

    def __init__(self, workspace_name: str, actions: list[dict[str, Any]]) -> None:
        self.workspace_name = workspace_name
        self.actions = actions
        self._registry = None          # VPN — lazy-loaded
        self._browser_registry = None  # Browser — lazy-loaded
        self._ide_registry = None      # IDE — lazy-loaded
        self._terminal_registry = None  # Terminal — lazy-loaded
        self._aerospace: object | None = _SENTINEL  # AeroSpace — lazy-loaded

    def _get_registry(self):
        """Return a VPNAdapterRegistry, initialising it on first call."""
        if self._registry is None:
            from ctx.adapters.vpn.registry import VPNAdapterRegistry
            self._registry = VPNAdapterRegistry()
        return self._registry

    def _get_browser_registry(self):
        """Return a BrowserAdapterRegistry, initialising it on first call."""
        if self._browser_registry is None:
            from ctx.adapters.browser.registry import BrowserAdapterRegistry
            self._browser_registry = BrowserAdapterRegistry()
        return self._browser_registry

    def _get_ide_registry(self):
        """Return an IDEAdapterRegistry, initialising it on first call."""
        if self._ide_registry is None:
            from ctx.adapters.ide.registry import IDEAdapterRegistry
            self._ide_registry = IDEAdapterRegistry()
        return self._ide_registry

    def _get_terminal_registry(self):
        """Return a TerminalAdapterRegistry, initialising it on first call."""
        if self._terminal_registry is None:
            from ctx.adapters.terminal.registry import TerminalAdapterRegistry
            self._terminal_registry = TerminalAdapterRegistry()
        return self._terminal_registry

    def _get_aerospace(self):
        """Return the active workspace manager adapter, or None. Cached after first call."""
        if self._aerospace is _SENTINEL:
            from ctx.adapters.wm.registry import WorkspaceManagerRegistry
            self._aerospace = WorkspaceManagerRegistry().detect_active()
        return self._aerospace

    def replay(self) -> None:
        """Execute all recorded actions in order."""
        print(f"[ctx] Replaying workspace '{self.workspace_name}' ({len(self.actions)} actions)")
        for i, action in enumerate(self.actions, start=1):
            action_type = action.get("type", "unknown")
            data = action.get("data", {})

            if action_type == "vpn_connect":
                self._handle_vpn_connect(i, action)
            elif action_type == "vpn_disconnect":
                self._handle_vpn_disconnect(i, action)
            elif action_type == "browser_tab_open":
                self._handle_browser_tab_open(i, action)
            elif action_type == "ide_project_open":
                self._handle_ide_project_open(i, action)
            elif action_type == "terminal_session_open":
                self._handle_terminal_session_open(i, action)
            elif action_type == "app_open":
                self._handle_app_open(i, action)
            else:
                print(f"  [{i:>3}] {action_type}: {data}")

        print("[ctx] Replay complete")

    # ------------------------------------------------------------------
    # VPN action handlers
    # ------------------------------------------------------------------

    def _handle_vpn_connect(self, index: int, action: dict[str, Any]) -> None:
        """Replay a vpn_connect action using the appropriate adapter."""
        client = action.get("client", "")
        profile = action.get("profile")
        print(f"  [{index:>3}] vpn_connect: client={client!r} profile={profile!r}")

        registry = self._get_registry()
        adapter = registry.get_adapter(client)

        if adapter is None:
            logger.warning(
                "Replayer: no adapter found for VPN client %r — skipping vpn_connect", client
            )
            print(f"         [warn] No adapter for '{client}' — skipping")
            return

        config = dict(action)  # pass full action dict as config

        def _attempt() -> bool:
            return adapter.connect(config)

        success = _retry_vpn_action(_attempt)
        if success:
            print(f"         [ok] Connected via {client}")
        else:
            logger.warning(
                "Replayer: vpn_connect via %r failed after 3 retries", client
            )
            print(f"         [warn] vpn_connect via '{client}' failed after 3 retries — continuing")

    def _handle_vpn_disconnect(self, index: int, action: dict[str, Any]) -> None:
        """Replay a vpn_disconnect action using the appropriate adapter."""
        client = action.get("client", "")
        print(f"  [{index:>3}] vpn_disconnect: client={client!r}")

        registry = self._get_registry()
        adapter = registry.get_adapter(client)

        if adapter is None:
            logger.warning(
                "Replayer: no adapter found for VPN client %r — skipping vpn_disconnect", client
            )
            print(f"         [warn] No adapter for '{client}' — skipping")
            return

        success = adapter.disconnect()
        if success:
            print(f"         [ok] Disconnected via {client}")
        else:
            logger.warning("Replayer: vpn_disconnect via %r failed", client)
            print(f"         [warn] vpn_disconnect via '{client}' failed — continuing")

    # ------------------------------------------------------------------
    # Browser action handlers
    # ------------------------------------------------------------------

    def _handle_browser_tab_open(self, index: int, action: dict[str, Any]) -> None:
        """Replay a browser_tab_open action using the appropriate adapter."""
        from ctx.adapters.wm.app_names import BROWSER_APP_NAMES
        browser = action.get("browser", "")
        url = action.get("url", "")
        workspace = action.get("workspace")
        print(f"  [{index:>3}] browser_tab_open: browser={browser!r} url={url!r}"
              + (f" workspace={workspace!r}" if workspace else ""))

        registry = self._get_browser_registry()
        adapter = registry.get_adapter(browser)

        if adapter is None:
            # Fall back to the system default browser
            result = subprocess.run(["open", url], capture_output=True)
            if result.returncode == 0:
                print(f"         [ok] Opened in default browser")
            else:
                logger.warning("Replayer: failed to open URL %r via default browser", url)
                print(f"         [warn] Failed to open URL — continuing")
            return

        opened = adapter.open_url(url)
        if opened:
            print(f"         [ok] Opened in {browser}")
        else:
            logger.warning("Replayer: browser_tab_open via %r failed for %r", browser, url)
            print(f"         [warn] Failed to open in '{browser}' — continuing")
            return

        if workspace:
            self._place_in_workspace(BROWSER_APP_NAMES.get(browser), workspace)

    # ------------------------------------------------------------------
    # IDE action handlers
    # ------------------------------------------------------------------

    def _handle_ide_project_open(self, index: int, action: dict[str, Any]) -> None:
        """Replay an ide_project_open action using the appropriate adapter."""
        from ctx.adapters.wm.app_names import IDE_APP_NAMES
        client = action.get("client", "")
        path = action.get("path", "")
        workspace = action.get("workspace")
        print(f"  [{index:>3}] ide_project_open: client={client!r} path={path!r}"
              + (f" workspace={workspace!r}" if workspace else ""))

        registry = self._get_ide_registry()
        adapter = registry.get_adapter(client)

        if adapter is None:
            logger.warning(
                "Replayer: no adapter found for IDE client %r — skipping ide_project_open", client
            )
            print(f"         [warn] No adapter for '{client}' — skipping")
            return

        if adapter.open_project(path):
            print(f"         [ok] Opened {path!r} in {client}")
        else:
            logger.warning(
                "Replayer: ide_project_open via %r failed for %r", client, path
            )
            print(f"         [warn] Failed to open {path!r} in '{client}' — continuing")
            return

        if workspace:
            self._place_in_workspace(IDE_APP_NAMES.get(client), workspace)

    # ------------------------------------------------------------------
    # Terminal action handlers
    # ------------------------------------------------------------------

    def _handle_terminal_session_open(self, index: int, action: dict[str, Any]) -> None:
        """Replay a terminal_session_open action using the appropriate adapter."""
        from ctx.adapters.wm.app_names import TERMINAL_APP_NAMES
        app = action.get("app", "")
        directory = action.get("directory", "")
        workspace = action.get("workspace")
        print(f"  [{index:>3}] terminal_session_open: app={app!r} directory={directory!r}"
              + (f" workspace={workspace!r}" if workspace else ""))

        registry = self._get_terminal_registry()
        adapter = registry.get_adapter(app)

        if adapter is None:
            logger.warning("Replayer: no adapter for terminal %r — skipping", app)
            print(f"         [warn] No adapter for '{app}' — skipping")
            return

        # Snapshot existing window IDs before opening so we can identify the new window
        aerospace = self._get_aerospace()
        app_os_name = TERMINAL_APP_NAMES.get(app)
        before_ids: set[int] = set()
        if workspace and aerospace and app_os_name:
            before_ids = set(aerospace.get_app_window_ids(app_os_name))

        if adapter.open_in_dir(directory):
            print(f"         [ok] Opened terminal in {directory!r} via {app}")
        else:
            logger.warning("Replayer: terminal_session_open via %r failed for %r", app, directory)
            print(f"         [warn] Failed to open terminal in {directory!r} — continuing")
            return

        if workspace and aerospace and app_os_name:
            time.sleep(_AEROSPACE_SETTLE)
            after_ids = set(aerospace.get_app_window_ids(app_os_name))
            new_ids = after_ids - before_ids
            # Move only the new window; fall back to any window of the app
            target_ids = new_ids or after_ids
            for wid in target_ids:
                aerospace.move_window_to_workspace(wid, workspace)
                break

    # ------------------------------------------------------------------
    # Generic app handler
    # ------------------------------------------------------------------

    def _handle_app_open(self, index: int, action: dict[str, Any]) -> None:
        """Replay an app_open action by launching the app with 'open -a'."""
        app_name = action.get("app_name", "")
        workspace = action.get("workspace")
        print(f"  [{index:>3}] app_open: {app_name!r}"
              + (f" workspace={workspace!r}" if workspace else ""))

        result = subprocess.run(["open", "-a", app_name], capture_output=True)
        if result.returncode != 0:
            logger.warning("Replayer: could not open app %r", app_name)
            print(f"         [warn] Could not open {app_name!r} — app may not be installed")
            return

        print(f"         [ok] Launched {app_name!r}")

        if workspace:
            self._place_in_workspace(app_name, workspace)

    # ------------------------------------------------------------------
    # AeroSpace workspace placement helper
    # ------------------------------------------------------------------

    def _place_in_workspace(self, app_os_name: str | None, workspace: str) -> None:
        """Move the first window of *app_os_name* to *workspace* after a settle delay."""
        if not app_os_name:
            return
        aerospace = self._get_aerospace()
        if aerospace is None:
            return
        time.sleep(_AEROSPACE_SETTLE)
        moved = aerospace.move_app_to_workspace(app_os_name, workspace)
        if moved:
            print(f"         [ok] Moved to AeroSpace workspace {workspace!r}")
        else:
            logger.warning(
                "Replayer: could not move %r to workspace %r", app_os_name, workspace
            )
            print(f"         [warn] Could not move to workspace {workspace!r}")
