"""Executes a FocusPlan step by step."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field

import click

from spaceload.focus.focus_planner import FocusPlan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-browser tab close via AppleScript
# ---------------------------------------------------------------------------

_CLOSE_TAB_SCRIPTS: dict[str, str] = {
    "chrome": """\
tell application "Google Chrome"
    set targetURL to "{url}"
    repeat with w in windows
        set tabList to tabs of w
        set i to count of tabList
        repeat while i > 0
            if URL of item i of tabList is targetURL then
                close item i of tabList
            end if
            set i to i - 1
        end repeat
    end repeat
end tell
""",
    "arc": """\
tell application "Arc"
    set targetURL to "{url}"
    repeat with w in windows
        set tabList to tabs of w
        set i to count of tabList
        repeat while i > 0
            if URL of item i of tabList is targetURL then
                close item i of tabList
            end if
            set i to i - 1
        end repeat
    end repeat
end tell
""",
    "safari": """\
tell application "Safari"
    set targetURL to "{url}"
    repeat with w in windows
        set tabList to tabs of w
        set i to count of tabList
        repeat while i > 0
            if URL of item i of tabList is targetURL then
                close item i of tabList
            end if
            set i to i - 1
        end repeat
    end repeat
end tell
""",
}


def _close_tab(url: str, browser: str) -> bool:
    """Close *url* in *browser* using AppleScript. Returns True on success."""
    script_tmpl = _CLOSE_TAB_SCRIPTS.get(browser)
    if script_tmpl is None:
        logger.debug("_close_tab: no AppleScript for browser %r", browser)
        return False
    # Escape double-quotes inside the URL to avoid breaking the AppleScript string
    safe_url = url.replace('"', '\\"')
    script = script_tmpl.format(url=safe_url)
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("_close_tab: osascript error for %r: %s", url, exc)
        return False


# ---------------------------------------------------------------------------
# Stats accumulator
# ---------------------------------------------------------------------------

@dataclass
class FocusStats:
    opened: int = 0
    closed: int = 0
    kept: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class FocusExecutor:
    """Executes a FocusPlan produced by FocusPlanner."""

    def execute(
        self,
        plan: FocusPlan,
        yes: bool = False,
        verbose: bool = False,
    ) -> FocusStats:
        stats = FocusStats()

        # Step 1: browser tab closes (with confirmation)
        if plan.tabs_to_close:
            self._handle_close_tabs(plan, yes, stats, verbose)

        # Step 2: open workspace tabs not already open
        self._handle_open_tabs(plan, stats, verbose)

        # Step 3: open IDE projects
        self._handle_ide(plan, stats, verbose)

        # Step 4: start Docker services
        self._handle_docker(plan, stats, verbose)

        # Step 5: open terminal sessions
        self._handle_terminals(plan, stats, verbose)

        return stats

    # ------------------------------------------------------------------

    def _handle_close_tabs(
        self,
        plan: FocusPlan,
        yes: bool,
        stats: FocusStats,
        verbose: bool,
    ) -> None:
        count = len(plan.tabs_to_close)
        click.echo(f"\nThe following {count} browser tab(s) will be closed:\n")
        for url in plan.tabs_to_close:
            click.echo(f"  {url}")

        if plan.tabs_to_keep:
            click.echo(f"\nThese {len(plan.tabs_to_keep)} tab(s) will stay open (in workspace):\n")
            for url in plan.tabs_to_keep:
                click.echo(f"  {url}")

        if plan.keep_matched:
            click.echo(f"\nThese {len(plan.keep_matched)} tab(s) will stay open (matched --keep):\n")
            for url in plan.keep_matched:
                click.echo(f"  {url}")

        if not yes:
            confirmed = click.confirm(f"\nClose the {count} tab(s) and continue?", default=False)
            if not confirmed:
                click.echo("[focus] Skipping all tab closes — continuing with opens only.")
                return

        for url in plan.tabs_to_close:
            browser = plan._tab_browser_map.get(url, "")
            ok = _close_tab(url, browser)
            if ok:
                if verbose:
                    click.echo(f"  [closed] {url}")
                stats.closed += 1
            else:
                click.echo(f"  [warn] Could not close {url!r} (browser={browser!r})")
                stats.failed.append(url)

    def _handle_open_tabs(
        self,
        plan: FocusPlan,
        stats: FocusStats,
        verbose: bool,
    ) -> None:
        ws_tabs: dict[str, str] = getattr(plan, "_ws_tabs", {})
        for url in plan.tabs_to_open:
            browser = ws_tabs.get(url, "")
            opened = self._open_tab(url, browser)
            if opened:
                if verbose:
                    click.echo(f"  [opened] {url}")
                stats.opened += 1
            else:
                click.echo(f"  [warn] Could not open {url!r}")
                stats.failed.append(url)
        stats.kept += len(plan.tabs_to_keep) + len(plan.keep_matched)

    def _open_tab(self, url: str, browser: str) -> bool:
        try:
            from spaceload.adapters.browser.registry import BrowserAdapterRegistry
            registry = BrowserAdapterRegistry()
            adapter = registry.get_adapter(browser)
            if adapter is not None:
                return adapter.open_url(url)
        except Exception as exc:
            logger.debug("_open_tab: adapter error: %s", exc)
        # Fallback: system default browser
        result = subprocess.run(["open", url], capture_output=True)
        return result.returncode == 0

    def _handle_ide(
        self,
        plan: FocusPlan,
        stats: FocusStats,
        verbose: bool,
    ) -> None:
        ide_projects: list[tuple[str, str]] = getattr(plan, "_ide_projects", [])
        if not ide_projects:
            return
        try:
            from spaceload.adapters.ide.registry import IDEAdapterRegistry
            registry = IDEAdapterRegistry()
        except Exception as exc:
            logger.warning("FocusExecutor: could not load IDE registry: %s", exc)
            return

        for client, path in ide_projects:
            adapter = registry.get_adapter(client)
            if adapter is None:
                click.echo(f"  [warn] No IDE adapter for '{client}' — skipping {path!r}")
                stats.skipped += 1
                continue
            ok = adapter.open_project(path)
            if ok:
                if verbose:
                    click.echo(f"  [opened] {client} → {path}")
                stats.opened += 1
            else:
                click.echo(f"  [warn] Could not open {path!r} in {client}")
                stats.failed.append(path)

    def _handle_docker(
        self,
        plan: FocusPlan,
        stats: FocusStats,
        verbose: bool,
    ) -> None:
        already_running: list[str] = getattr(plan, "_services_already_running", [])
        for name in already_running:
            if verbose:
                click.echo(f"  [skip] {name} already running")
            stats.skipped += 1

        for name in plan.services_to_start:
            try:
                result = subprocess.run(
                    ["docker", "start", name],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    if verbose:
                        click.echo(f"  [started] docker: {name}")
                    stats.opened += 1
                else:
                    click.echo(f"  [warn] docker start {name!r} failed: {result.stderr.strip()}")
                    stats.failed.append(name)
            except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
                click.echo(f"  [warn] docker start {name!r} error: {exc}")
                stats.failed.append(name)

    def _handle_terminals(
        self,
        plan: FocusPlan,
        stats: FocusStats,
        verbose: bool,
    ) -> None:
        terminal_sessions: list[tuple[str, str]] = getattr(plan, "_terminal_sessions", [])
        if not terminal_sessions:
            return
        try:
            from spaceload.adapters.terminal.registry import TerminalAdapterRegistry
            registry = TerminalAdapterRegistry()
        except Exception as exc:
            logger.warning("FocusExecutor: could not load terminal registry: %s", exc)
            return

        for app, directory in terminal_sessions:
            adapter = registry.get_adapter(app)
            if adapter is None:
                click.echo(f"  [warn] No terminal adapter for '{app}' — skipping {directory!r}")
                stats.skipped += 1
                continue
            ok = adapter.open_in_dir(directory)
            if ok:
                if verbose:
                    click.echo(f"  [opened] {app} → {directory}")
                stats.opened += 1
            else:
                click.echo(f"  [warn] Could not open terminal in {directory!r}")
                stats.failed.append(directory)
