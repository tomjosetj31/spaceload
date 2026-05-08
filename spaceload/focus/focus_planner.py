"""Builds a FocusPlan from a saved workspace and the current environment."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field

from spaceload.focus.tab_matcher import any_pattern_matches

logger = logging.getLogger(__name__)


@dataclass
class FocusAction:
    action_type: str          # "open_tab", "close_tab", "open_ide",
                              # "start_docker", "open_terminal", "skip"
    target: str               # URL, path, container name, etc.
    reason: str               # human-readable explanation
    requires_confirmation: bool


@dataclass
class FocusPlan:
    workspace_name: str
    actions: list[FocusAction]
    tabs_to_open: list[str]
    tabs_to_close: list[str]
    tabs_to_keep: list[str]       # already open AND in workspace
    keep_matched: list[str]       # open tabs kept because of --keep patterns
    services_to_start: list[str]
    # Internal: maps URL → browser name for currently-open tabs (used by executor)
    _tab_browser_map: dict[str, str] = field(default_factory=dict, repr=False)


def _read_current_tabs() -> tuple[dict[str, str], bool]:
    """Return ({url: browser_name}, can_read) for all currently open browser tabs.

    ``can_read`` is False when no supported browser adapter was available.
    """
    try:
        from spaceload.adapters.browser.registry import BrowserAdapterRegistry
        registry = BrowserAdapterRegistry()
        adapters = registry.available_adapters()
    except Exception as exc:
        logger.warning("FocusPlanner: could not load browser registry: %s", exc)
        return {}, False

    tab_map: dict[str, str] = {}
    any_read = False
    for adapter in adapters:
        try:
            tabs = adapter.get_open_tabs()
            any_read = True
            for url in tabs:
                tab_map[url] = adapter.name
        except Exception as exc:
            logger.warning(
                "FocusPlanner: could not read tabs from %s: %s", adapter.name, exc
            )

    return tab_map, any_read


def _running_docker_containers() -> set[str]:
    """Return names of currently running Docker containers, or empty set."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {n.strip() for n in result.stdout.splitlines() if n.strip()}
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return set()


class FocusPlanner:
    """Builds a complete FocusPlan before any action is executed."""

    def build(
        self,
        workspace_actions: list[dict],
        keep_patterns: list[str],
        no_close: bool = False,
        close_terminals: bool = False,
    ) -> tuple[FocusPlan, bool]:
        """Build and return (FocusPlan, can_read_tabs).

        ``can_read_tabs`` is False when no browser adapter could be queried,
        in which case the caller should warn and skip all close actions.
        """
        # --- Extract workspace state from recorded actions ---
        ws_tabs: dict[str, str] = {}   # url → browser
        ide_projects: list[tuple[str, str]] = []    # (client, path)
        ws_containers: list[str] = []   # from last docker_containers action
        terminal_sessions: list[tuple[str, str]] = []  # (app, directory)

        # Track last docker_containers to avoid replaying stale state
        _last_docker: list[str] = []

        for action in workspace_actions:
            t = action.get("type", "")
            if t == "browser_tab_open":
                url = action.get("url", "")
                browser = action.get("browser", "")
                if url:
                    ws_tabs[url] = browser
            elif t == "ide_project_open":
                client = action.get("client", "")
                path = action.get("path", "")
                if client and path:
                    entry = (client, path)
                    if entry not in ide_projects:
                        ide_projects.append(entry)
            elif t == "docker_containers":
                _last_docker = action.get("containers", [])
            elif t == "terminal_session_open":
                app = action.get("app", "")
                directory = action.get("directory", "")
                if app and directory:
                    entry = (app, directory)
                    if entry not in terminal_sessions:
                        terminal_sessions.append(entry)

        ws_containers = _last_docker

        # --- Read current environment ---
        current_tabs, can_read_tabs = _read_current_tabs()
        running_containers = _running_docker_containers()

        # --- Compute tab categories ---
        tabs_to_keep: list[str] = []
        tabs_to_open: list[str] = []
        tabs_to_close: list[str] = []
        keep_matched: list[str] = []

        ws_url_set = set(ws_tabs)

        # Classify currently open tabs
        if can_read_tabs:
            for url in current_tabs:
                if url in ws_url_set:
                    tabs_to_keep.append(url)
                elif any_pattern_matches(url, keep_patterns):
                    keep_matched.append(url)
                else:
                    tabs_to_close.append(url)

        # Workspace tabs not currently open → open them
        current_url_set = set(current_tabs)
        for url in ws_tabs:
            if url not in current_url_set:
                tabs_to_open.append(url)

        # Docker: only start containers not already running
        services_to_start = [c for c in ws_containers if c not in running_containers]
        services_already_running = [c for c in ws_containers if c in running_containers]

        # --- Build ordered action list ---
        actions: list[FocusAction] = []

        if not no_close and can_read_tabs:
            for url in tabs_to_close:
                actions.append(FocusAction(
                    action_type="close_tab",
                    target=url,
                    reason="not in workspace",
                    requires_confirmation=True,
                ))

        for url in tabs_to_open:
            browser = ws_tabs[url]
            actions.append(FocusAction(
                action_type="open_tab",
                target=url,
                reason=f"in workspace ({browser})",
                requires_confirmation=False,
            ))

        for client, path in ide_projects:
            actions.append(FocusAction(
                action_type="open_ide",
                target=path,
                reason=f"workspace IDE project ({client})",
                requires_confirmation=False,
            ))

        for name in services_to_start:
            actions.append(FocusAction(
                action_type="start_docker",
                target=name,
                reason="workspace service, not running",
                requires_confirmation=False,
            ))

        for name in services_already_running:
            actions.append(FocusAction(
                action_type="skip",
                target=name,
                reason="already running",
                requires_confirmation=False,
            ))

        for app, directory in terminal_sessions:
            actions.append(FocusAction(
                action_type="open_terminal",
                target=directory,
                reason=f"workspace terminal session ({app})",
                requires_confirmation=False,
            ))

        plan = FocusPlan(
            workspace_name="",  # set by caller
            actions=actions,
            tabs_to_open=tabs_to_open,
            tabs_to_close=tabs_to_close if (not no_close and can_read_tabs) else [],
            tabs_to_keep=tabs_to_keep,
            keep_matched=keep_matched,
            services_to_start=services_to_start,
            _tab_browser_map=current_tabs,
        )
        # Attach metadata needed by executor
        plan._ide_projects = ide_projects  # type: ignore[attr-defined]
        plan._terminal_sessions = terminal_sessions  # type: ignore[attr-defined]
        plan._ws_tabs = ws_tabs  # type: ignore[attr-defined]
        plan._services_already_running = services_already_running  # type: ignore[attr-defined]

        return plan, can_read_tabs
