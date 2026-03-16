"""Pure diff engine for comparing two workspace action lists.

This module has no side effects and performs no I/O — all functions are
pure. It is designed to be fully unit-testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DiffItem:
    """A single diff entry for one resource."""

    category: str        # "browser", "ide", "terminal", "vpn", "app"
    status: str          # "added", "removed", "unchanged"
    label: str           # human-readable description shown in the diff
    old_value: str | None = None
    new_value: str | None = None


@dataclass
class DiffResult:
    """The complete result of comparing two workspaces."""

    items: list[DiffItem] = field(default_factory=list)
    added: int = 0
    removed: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.added + self.removed + self.unchanged


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _browser_tabs(actions: list[dict]) -> dict[str, set[str]]:
    """Return {browser_name: {url, ...}} from a list of actions."""
    result: dict[str, set[str]] = {}
    for a in actions:
        if a.get("type") == "browser_tab_open":
            browser = a.get("browser", "browser")
            url = a.get("url", "")
            if url:
                result.setdefault(browser, set()).add(url)
    return result


def _ide_projects(actions: list[dict]) -> dict[str, set[str]]:
    """Return {client_name: {path, ...}} from a list of actions."""
    result: dict[str, set[str]] = {}
    for a in actions:
        if a.get("type") == "ide_project_open":
            client = a.get("client", "ide")
            path = a.get("path", "")
            if path:
                result.setdefault(client, set()).add(path)
    return result


def _terminal_sessions(actions: list[dict]) -> dict[str, set[str]]:
    """Return {app_name: {directory, ...}} from a list of actions."""
    result: dict[str, set[str]] = {}
    for a in actions:
        if a.get("type") == "terminal_session_open":
            app = a.get("app", "terminal")
            directory = a.get("directory", "")
            if directory:
                result.setdefault(app, set()).add(directory)
    return result


def _vpn_connections(actions: list[dict]) -> set[str]:
    """Return {'{client}:{profile}'} for connected VPNs."""
    result: set[str] = set()
    for a in actions:
        if a.get("type") == "vpn_connect":
            client = a.get("client", "vpn")
            profile = a.get("profile") or ""
            result.add(f"{client}:{profile}" if profile else client)
    return result


def _app_opens(actions: list[dict]) -> set[str]:
    """Return {app_name} from app_open actions."""
    return {
        a.get("app_name", "")
        for a in actions
        if a.get("type") == "app_open" and a.get("app_name")
    }


def _diff_sets(
    category: str,
    label_fn,
    old_set: set[str],
    new_set: set[str],
) -> list[DiffItem]:
    """Produce DiffItems for two flat sets of string values."""
    items: list[DiffItem] = []
    for val in sorted(old_set - new_set):
        items.append(DiffItem(category=category, status="removed", label=label_fn(val), old_value=val))
    for val in sorted(new_set - old_set):
        items.append(DiffItem(category=category, status="added", label=label_fn(val), new_value=val))
    for val in sorted(old_set & new_set):
        items.append(DiffItem(category=category, status="unchanged", label=label_fn(val), old_value=val, new_value=val))
    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def diff(old_actions: list[dict], new_actions: list[dict]) -> DiffResult:
    """Compare two action lists and return a DiffResult.

    Parameters
    ----------
    old_actions:
        Actions from the saved workspace (the baseline).
    new_actions:
        Actions from the other workspace or current environment (the comparison).

    Returns
    -------
    DiffResult
        Pure data — no I/O, no side effects.
    """
    items: list[DiffItem] = []

    # --- Browser tabs ---
    old_browsers = _browser_tabs(old_actions)
    new_browsers = _browser_tabs(new_actions)
    all_browsers = sorted(old_browsers.keys() | new_browsers.keys())
    for browser in all_browsers:
        old_urls = old_browsers.get(browser, set())
        new_urls = new_browsers.get(browser, set())
        items.extend(
            _diff_sets(
                "browser",
                lambda url, b=browser: f"{b}: {url}",
                old_urls,
                new_urls,
            )
        )

    # --- IDE projects ---
    old_ides = _ide_projects(old_actions)
    new_ides = _ide_projects(new_actions)
    all_ides = sorted(old_ides.keys() | new_ides.keys())
    for client in all_ides:
        old_paths = old_ides.get(client, set())
        new_paths = new_ides.get(client, set())
        items.extend(
            _diff_sets(
                "ide",
                lambda path, c=client: f"{c} \u2192 {path}",
                old_paths,
                new_paths,
            )
        )

    # --- Terminal sessions ---
    old_terminals = _terminal_sessions(old_actions)
    new_terminals = _terminal_sessions(new_actions)
    all_terminals = sorted(old_terminals.keys() | new_terminals.keys())
    for app in all_terminals:
        old_dirs = old_terminals.get(app, set())
        new_dirs = new_terminals.get(app, set())
        items.extend(
            _diff_sets(
                "terminal",
                lambda d, a=app: f"{a}: {d}",
                old_dirs,
                new_dirs,
            )
        )

    # --- VPN ---
    old_vpn = _vpn_connections(old_actions)
    new_vpn = _vpn_connections(new_actions)
    items.extend(_diff_sets("vpn", lambda v: v, old_vpn, new_vpn))

    # --- Generic apps ---
    old_apps = _app_opens(old_actions)
    new_apps = _app_opens(new_actions)
    items.extend(_diff_sets("app", lambda a: a, old_apps, new_apps))

    added = sum(1 for i in items if i.status == "added")
    removed = sum(1 for i in items if i.status == "removed")
    unchanged = sum(1 for i in items if i.status == "unchanged")

    return DiffResult(items=items, added=added, removed=removed, unchanged=unchanged)
