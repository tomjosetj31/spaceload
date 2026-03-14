"""Unix socket recorder daemon for ctx.

Run as a subprocess by `ctx record <name>`. Listens for JSON messages on a
Unix domain socket, accumulates actions in memory, and flushes them to the
SQLite store on a stop command.

Usage (internal — spawned by the CLI):
    python -m loadout.daemon.server <workspace_name> [--db <db_path>]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# Make sure the project root is importable when run as __main__
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from loadout.store.workspace_store import WorkspaceStore
from loadout.adapters.vpn.registry import VPNAdapterRegistry
from loadout.adapters.browser.registry import BrowserAdapterRegistry
from loadout.adapters.ide.registry import IDEAdapterRegistry
from loadout.adapters.terminal.registry import TerminalAdapterRegistry
from loadout.adapters.wm.registry import WorkspaceManagerRegistry
from loadout.adapters.wm.app_names import BROWSER_APP_NAMES, IDE_APP_NAMES, TERMINAL_APP_NAMES

_LOADOUT_DIR = Path.home() / ".loadout"
_SOCKET_PATH = _LOADOUT_DIR / "daemon.sock"
_PID_PATH = _LOADOUT_DIR / "daemon.pid"
_LOG_PATH = _LOADOUT_DIR / "daemon.log"

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure logging to write to both file and capture debug info."""
    _LOADOUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create a file handler with detailed formatting
    file_handler = logging.FileHandler(_LOG_PATH, mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    
    # Configure root logger to capture all logs
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    
    # Also add a stream handler for immediate visibility during development
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger.addHandler(stream_handler)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VPNPoller:
    """Background thread that polls VPN state and appends events to the action log.

    Polls every *poll_interval* seconds. On a state transition
    (None→connected or connected→None) it appends a ``vpn_connect`` or
    ``vpn_disconnect`` action dict to the shared *actions* list.
    """

    def __init__(
        self,
        actions: list[dict],
        poll_interval: float = 2.0,
    ) -> None:
        self._actions = actions
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_state: bool | None = None  # None = unknown, True = connected
        self._last_client: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the polling thread."""
        self._thread = threading.Thread(target=self._run, daemon=True, name="vpn-poller")
        self._thread.start()

    def stop(self) -> None:
        """Signal the polling thread to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 1)

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main polling loop — runs in a background thread."""
        try:
            registry = VPNAdapterRegistry()
        except Exception as exc:
            logger.warning("VPNPoller: could not initialise registry: %s", exc)
            return

        while not self._stop_event.is_set():
            try:
                self._poll(registry)
            except Exception as exc:
                logger.warning("VPNPoller: poll error: %s", exc)
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll(self, registry) -> None:
        """Check current VPN state and emit an event if it changed."""
        result = registry.detect_active()
        if result is not None:
            _adapter, state = result
            currently_connected = True
            client = state.client
            profile = state.profile
        else:
            currently_connected = False
            client = self._last_client
            profile = None

        if self._last_state is None:
            # First poll — record baseline without emitting an event
            self._last_state = currently_connected
            self._last_client = client
            logger.debug("VPNPoller: baseline state connected=%s client=%s", currently_connected, client)
            return

        if currently_connected and not self._last_state:
            # Transition: disconnected → connected
            action = {
                "type": "vpn_connect",
                "client": client,
                "profile": profile,
                "timestamp": _now_iso(),
            }
            self._actions.append(action)
            logger.info("VPNPoller: RECORDED vpn_connect client=%s profile=%s", client, profile)
            self._last_client = client
        elif not currently_connected and self._last_state:
            # Transition: connected → disconnected
            action = {
                "type": "vpn_disconnect",
                "client": self._last_client,
                "timestamp": _now_iso(),
            }
            self._actions.append(action)
            logger.info("VPNPoller: RECORDED vpn_disconnect client=%s", self._last_client)

        self._last_state = currently_connected
        if currently_connected:
            self._last_client = client


class BrowserPoller:
    """Background thread that polls browser tabs and records new tab-open events.

    On the first poll the open tab set is recorded as a baseline.  On each
    subsequent poll, any URLs that are new for a given browser are emitted as
    ``browser_tab_open`` actions.
    
    Smart filtering:
    - Filters out blank/newtab pages (chrome://newtab/, about:blank, etc.)
    - Tracks URLs for a stabilization period before recording (filters redirects)
    - Deduplicates URLs from the same domain in quick succession
    """

    # URLs to always ignore (blank pages, new tabs, etc.)
    # Covers: Chrome, Safari, Firefox, Edge, Arc, Brave, Opera, Vivaldi
    _IGNORED_URL_PATTERNS: frozenset[str] = frozenset({
        # Chrome / Chromium-based (Chrome, Edge, Brave, Arc, Opera, Vivaldi)
        "chrome://newtab",
        "chrome://newtab/",
        "chrome://new-tab-page",
        "chrome://new-tab-page/",
        # Edge
        "edge://newtab",
        "edge://newtab/",
        # Brave
        "brave://newtab",
        "brave://newtab/",
        # Firefox
        "about:newtab",
        "about:home",
        "about:blank",
        "about:privatebrowsing",
        # Safari
        "favorites://",
        "safari-resource:/",
        # Opera
        "opera://startpage",
        "opera://startpage/",
        # Vivaldi
        "vivaldi://newtab",
        "vivaldi://newtab/",
        # Arc
        "arc://newtab",
        "arc://newtab/",
    })
    
    # URL prefixes to ignore (internal browser pages)
    # Covers: Chrome, Safari, Firefox, Edge, Arc, Brave, Opera, Vivaldi
    _IGNORED_URL_PREFIXES: tuple[str, ...] = (
        # Chrome / Chromium-based
        "chrome://",
        "chrome-extension://",
        # Edge
        "edge://",
        # Brave  
        "brave://",
        # Firefox
        "about:",
        "moz-extension://",
        "resource://",
        # Safari
        "safari-resource:",
        "favorites:",
        "safari-extension:",
        # Opera
        "opera://",
        # Vivaldi
        "vivaldi://",
        # Arc
        "arc://",
        # Local files (usually not intended to record)
        "file://",
        # Data URLs (embedded content)
        "data:",
        # Blob URLs (temporary)
        "blob:",
        # JavaScript URLs
        "javascript:",
    )
    
    # How long (in seconds) a URL must be "stable" before recording
    _STABILIZATION_TIME: float = 3.0

    def __init__(
        self,
        actions: list[dict],
        poll_interval: float = 2.0,
        stabilization_time: float | None = None,
        domain_cooldown: float | None = None,
        include_open: bool = False,
    ) -> None:
        self._actions = actions
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Per-browser baseline: browser name → set of known URLs
        self._known_tabs: dict[str, set[str]] = {}
        # Pending URLs waiting for stabilization: browser → {url: first_seen_time}
        self._pending_urls: dict[str, dict[str, float]] = {}
        # Recently recorded domains to prevent duplicates: browser → {domain: last_record_time}
        self._recent_domains: dict[str, dict[str, float]] = {}
        # Configurable stabilization time (defaults to class constant)
        self._stabilization_time = stabilization_time if stabilization_time is not None else self._STABILIZATION_TIME
        # Cooldown for same domain (seconds)
        self._domain_cooldown: float = domain_cooldown if domain_cooldown is not None else 5.0
        # Whether to record already-open tabs on start
        self._include_open = include_open

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the polling thread."""
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="browser-poller"
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the polling thread to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 1)

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main polling loop — runs in a background thread."""
        try:
            registry = BrowserAdapterRegistry()
        except Exception as exc:
            logger.warning("BrowserPoller: could not initialise registry: %s", exc)
            return

        aerospace = WorkspaceManagerRegistry().detect_active()

        while not self._stop_event.is_set():
            try:
                self._poll(registry, aerospace)
            except Exception as exc:
                logger.warning("BrowserPoller: poll error: %s", exc)
            self._stop_event.wait(timeout=self._poll_interval)

    def _should_ignore_url(self, url: str) -> bool:
        """Check if URL should be ignored (blank pages, internal pages, etc.)."""
        if not url:
            return True
        
        # Check exact matches
        if url in self._IGNORED_URL_PATTERNS:
            return True
        
        # Check prefixes
        if url.startswith(self._IGNORED_URL_PREFIXES):
            return True
        
        return False

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL for deduplication."""
        try:
            # Remove protocol
            if "://" in url:
                url = url.split("://", 1)[1]
            # Get domain (before first /)
            domain = url.split("/")[0]
            # Remove port if present
            domain = domain.split(":")[0]
            # Remove www. prefix for comparison
            if domain.startswith("www."):
                domain = domain[4:]
            return domain.lower()
        except Exception:
            return url

    def _is_domain_on_cooldown(self, browser: str, domain: str, now: float) -> bool:
        """Check if we recently recorded a URL from this domain."""
        if browser not in self._recent_domains:
            return False
        recent = self._recent_domains[browser]
        if domain in recent:
            if now - recent[domain] < self._domain_cooldown:
                return True
        return False

    def _record_domain(self, browser: str, domain: str, now: float) -> None:
        """Record that we just recorded a URL from this domain."""
        if browser not in self._recent_domains:
            self._recent_domains[browser] = {}
        self._recent_domains[browser][domain] = now
        
        # Clean up old entries
        cutoff = now - self._domain_cooldown * 2
        self._recent_domains[browser] = {
            d: t for d, t in self._recent_domains[browser].items()
            if t > cutoff
        }

    def _poll(self, registry, aerospace: object | None) -> None:
        """Check current browser tabs and emit events for newly opened URLs.
        
        Uses smart filtering to avoid recording:
        - Blank/newtab pages
        - Intermediate URLs during navigation (waits for stabilization)
        - Multiple URLs from same domain in quick succession (redirect chains)
        """
        now = time.time()
        
        for adapter in registry.available_adapters():
            current_urls = set(adapter.get_open_tabs())
            logger.debug("BrowserPoller: %s has %d tabs", adapter.name, len(current_urls))
            
            if adapter.name not in self._known_tabs:
                # First time seeing this browser — set baseline
                self._known_tabs[adapter.name] = current_urls
                self._pending_urls[adapter.name] = {}
                
                if self._include_open:
                    # Record all currently open tabs (skip ignored URLs)
                    logger.debug("BrowserPoller: %s baseline with %d tabs - recording all", adapter.name, len(current_urls))
                    for url in sorted(current_urls):
                        if self._should_ignore_url(url):
                            continue
                        action: dict = {
                            "type": "browser_tab_open",
                            "browser": adapter.name,
                            "url": url,
                            "timestamp": _now_iso(),
                        }
                        if aerospace is not None:
                            app_name = BROWSER_APP_NAMES.get(adapter.name)
                            if app_name:
                                ws = aerospace.get_app_workspace(app_name)
                                if ws:
                                    action["workspace"] = ws
                        self._actions.append(action)
                        logger.info("BrowserPoller: RECORDED browser_tab_open (baseline) browser=%s url=%s", adapter.name, url)
                else:
                    logger.debug("BrowserPoller: %s baseline set with %d tabs", adapter.name, len(current_urls))
                continue
            
            # Find new URLs
            new_urls = current_urls - self._known_tabs[adapter.name]
            
            # Initialize pending dict for this browser if needed
            if adapter.name not in self._pending_urls:
                self._pending_urls[adapter.name] = {}
            pending = self._pending_urls[adapter.name]
            
            # Add new URLs to pending (if not ignored)
            for url in new_urls:
                if self._should_ignore_url(url):
                    logger.debug("BrowserPoller: ignoring URL %s", url)
                    continue
                if url not in pending:
                    pending[url] = now
                    logger.debug("BrowserPoller: URL pending stabilization: %s", url)
            
            # Remove URLs that are no longer open from pending
            pending_urls_list = list(pending.keys())
            for url in pending_urls_list:
                if url not in current_urls:
                    del pending[url]
                    logger.debug("BrowserPoller: URL closed before stabilization: %s", url)
            
            # Check which pending URLs have stabilized
            urls_to_record = []
            for url, first_seen in list(pending.items()):
                if now - first_seen >= self._stabilization_time:
                    # URL has been stable long enough
                    domain = self._extract_domain(url)
                    
                    # Check domain cooldown (to filter redirect chains)
                    if self._is_domain_on_cooldown(adapter.name, domain, now):
                        logger.debug("BrowserPoller: skipping URL (domain cooldown): %s", url)
                        del pending[url]
                        continue
                    
                    urls_to_record.append(url)
                    del pending[url]
            
            # Record stabilized URLs
            for url in urls_to_record:
                domain = self._extract_domain(url)
                
                action: dict = {
                    "type": "browser_tab_open",
                    "browser": adapter.name,
                    "url": url,
                    "timestamp": _now_iso(),
                }
                if aerospace is not None:
                    app_name = BROWSER_APP_NAMES.get(adapter.name)
                    if app_name:
                        ws = aerospace.get_app_workspace(app_name)
                        if ws:
                            action["workspace"] = ws
                self._actions.append(action)
                self._record_domain(adapter.name, domain, now)
                logger.info("BrowserPoller: RECORDED browser_tab_open browser=%s url=%s", adapter.name, url)
            
            # Update known tabs
            self._known_tabs[adapter.name] = current_urls


class IDEPoller:
    """Background thread that polls IDE projects and records new project-open events.

    On the first poll for each IDE the open project set is recorded as a
    baseline.  Subsequent polls emit ``ide_project_open`` actions for any
    paths that are new.
    """

    def __init__(
        self,
        actions: list[dict],
        poll_interval: float = 5.0,
        include_open: bool = False,
    ) -> None:
        self._actions = actions
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Per-IDE baseline: client name → set of known project paths
        self._known_projects: dict[str, set[str]] = {}
        # Whether to record already-open projects on start
        self._include_open = include_open

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the polling thread."""
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="ide-poller"
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the polling thread to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 1)

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main polling loop — runs in a background thread."""
        try:
            registry = IDEAdapterRegistry()
        except Exception as exc:
            logger.warning("IDEPoller: could not initialise registry: %s", exc)
            return

        aerospace = WorkspaceManagerRegistry().detect_active()

        while not self._stop_event.is_set():
            try:
                self._poll(registry, aerospace)
            except Exception as exc:
                logger.warning("IDEPoller: poll error: %s", exc)
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll(self, registry, aerospace: object | None) -> None:
        """Check current IDE projects and emit events for newly opened paths."""
        for adapter in registry.available_adapters():
            current_paths = set(adapter.get_open_projects())
            logger.debug("IDEPoller: %s has %d projects", adapter.name, len(current_paths))
            if adapter.name not in self._known_projects:
                # First time seeing this IDE — set baseline
                self._known_projects[adapter.name] = current_paths
                
                if self._include_open:
                    # Record all currently open projects
                    logger.debug("IDEPoller: %s baseline with %d projects - recording all", adapter.name, len(current_paths))
                    for path in sorted(current_paths):
                        action: dict = {
                            "type": "ide_project_open",
                            "client": adapter.name,
                            "path": path,
                            "timestamp": _now_iso(),
                        }
                        if aerospace is not None:
                            app_name = IDE_APP_NAMES.get(adapter.name)
                            if app_name:
                                ws = aerospace.get_app_workspace(app_name)
                                if ws:
                                    action["workspace"] = ws
                        self._actions.append(action)
                        logger.info("IDEPoller: RECORDED ide_project_open (baseline) client=%s path=%s", adapter.name, path)
                else:
                    logger.debug("IDEPoller: %s baseline set with %d projects", adapter.name, len(current_paths))
                continue
            new_paths = current_paths - self._known_projects[adapter.name]
            for path in sorted(new_paths):
                action: dict = {
                    "type": "ide_project_open",
                    "client": adapter.name,
                    "path": path,
                    "timestamp": _now_iso(),
                }
                if aerospace is not None:
                    app_name = IDE_APP_NAMES.get(adapter.name)
                    if app_name:
                        ws = aerospace.get_app_workspace(app_name)
                        if ws:
                            action["workspace"] = ws
                self._actions.append(action)
                logger.info("IDEPoller: RECORDED ide_project_open client=%s path=%s", adapter.name, path)
            self._known_projects[adapter.name] = current_paths


class TerminalPoller:
    """Background thread that polls terminal sessions and records events.

    Tracks terminal sessions by their unique identifiers (e.g., tty paths) to detect:
    1. New terminal tabs/windows opening (even in same directory)
    2. Directory changes within existing sessions
    
    On the first poll for each terminal adapter, sessions are recorded as baseline.
    Subsequent polls emit ``terminal_session_open`` actions for new sessions and
    ``terminal_dir_change`` actions when existing sessions change directories.
    """

    def __init__(
        self,
        actions: list[dict],
        poll_interval: float = 5.0,
        include_open: bool = False,
    ) -> None:
        self._actions = actions
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Per-adapter baseline: adapter name → dict of session_id → directory
        self._known_sessions: dict[str, dict[str, str]] = {}
        # Legacy fallback: adapter name → set of known directories
        self._known_dirs: dict[str, set[str]] = {}
        # Whether to record already-open terminals on start
        self._include_open = include_open

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the polling thread."""
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="terminal-poller"
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the polling thread to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 1)

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main polling loop — runs in a background thread."""
        try:
            registry = TerminalAdapterRegistry()
        except Exception as exc:
            logger.warning("TerminalPoller: could not initialise registry: %s", exc)
            return

        aerospace = WorkspaceManagerRegistry().detect_active()

        while not self._stop_event.is_set():
            try:
                self._poll(registry, aerospace)
            except Exception as exc:
                logger.warning("TerminalPoller: poll error: %s", exc)
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll(self, registry, aerospace: object | None) -> None:
        """Check current terminal sessions and emit events for changes."""
        for adapter in registry.available_adapters():
            # Try session-based tracking first (more accurate)
            try:
                sessions = adapter.get_sessions()
                self._poll_sessions(adapter.name, sessions, aerospace)
            except AttributeError:
                # Fall back to directory-based tracking for adapters without get_sessions
                self._poll_dirs_legacy(adapter, aerospace)

    def _poll_sessions(self, adapter_name: str, sessions: list, aerospace: object | None) -> None:
        """Poll using session-based tracking (tracks individual terminal tabs/windows)."""
        # Build current session map: session_id → directory
        current_sessions = {s.session_id: s.directory for s in sessions}
        
        logger.debug("TerminalPoller: %s has %d sessions: %s", 
                    adapter_name, len(current_sessions), current_sessions)
        
        if adapter_name not in self._known_sessions:
            # First time seeing this adapter — set baseline
            self._known_sessions[adapter_name] = current_sessions.copy()
            
            if self._include_open:
                # Record all currently open sessions
                logger.debug("TerminalPoller: %s baseline with %d sessions - recording all", 
                            adapter_name, len(current_sessions))
                for session_id, directory in current_sessions.items():
                    action: dict = {
                        "type": "terminal_session_open",
                        "app": adapter_name,
                        "directory": directory,
                        "session_id": session_id,
                        "timestamp": _now_iso(),
                    }
                    if aerospace is not None:
                        app_name = TERMINAL_APP_NAMES.get(adapter_name)
                        if app_name:
                            ws = aerospace.get_app_workspace(app_name)
                            if ws:
                                action["workspace"] = ws
                    self._actions.append(action)
                    logger.info("TerminalPoller: RECORDED terminal_session_open (baseline) app=%s dir=%s session=%s", 
                               adapter_name, directory, session_id)
            else:
                logger.debug("TerminalPoller: %s baseline set with %d sessions", 
                            adapter_name, len(current_sessions))
            return
        
        known = self._known_sessions[adapter_name]
        
        # Detect new sessions (new terminal tabs/windows)
        for session_id, directory in current_sessions.items():
            if session_id not in known:
                # New terminal session opened
                action: dict = {
                    "type": "terminal_session_open",
                    "app": adapter_name,
                    "directory": directory,
                    "session_id": session_id,
                    "timestamp": _now_iso(),
                }
                if aerospace is not None:
                    app_name = TERMINAL_APP_NAMES.get(adapter_name)
                    if app_name:
                        ws = aerospace.get_app_workspace(app_name)
                        if ws:
                            action["workspace"] = ws
                self._actions.append(action)
                logger.info("TerminalPoller: RECORDED terminal_session_open app=%s dir=%s session=%s", 
                           adapter_name, directory, session_id)
            elif known[session_id] != directory:
                # Existing session changed directory
                action = {
                    "type": "terminal_dir_change",
                    "app": adapter_name,
                    "directory": directory,
                    "previous_directory": known[session_id],
                    "session_id": session_id,
                    "timestamp": _now_iso(),
                }
                self._actions.append(action)
                logger.info("TerminalPoller: RECORDED terminal_dir_change app=%s %s -> %s", 
                           adapter_name, known[session_id], directory)
        
        # Update known sessions
        self._known_sessions[adapter_name] = current_sessions.copy()

    def _poll_dirs_legacy(self, adapter, aerospace: object | None) -> None:
        """Legacy polling using directory-based tracking."""
        current_dirs = set(adapter.get_open_dirs())
        logger.debug("TerminalPoller: %s has %d dirs: %s", adapter.name, len(current_dirs), current_dirs)
        
        if adapter.name not in self._known_dirs:
            # First time seeing this adapter — record baseline, no events
            self._known_dirs[adapter.name] = current_dirs
            logger.debug("TerminalPoller: %s baseline set with %d dirs", adapter.name, len(current_dirs))
            return
        
        new_dirs = current_dirs - self._known_dirs[adapter.name]
        for path in sorted(new_dirs):
            action: dict = {
                "type": "terminal_session_open",
                "app": adapter.name,
                "directory": path,
                "timestamp": _now_iso(),
            }
            if aerospace is not None:
                app_name = TERMINAL_APP_NAMES.get(adapter.name)
                if app_name:
                    ws = aerospace.get_app_workspace(app_name)
                    if ws:
                        action["workspace"] = ws
            self._actions.append(action)
            logger.info("TerminalPoller: RECORDED terminal_session_open app=%s dir=%s", adapter.name, path)
        
        self._known_dirs[adapter.name] = current_dirs


def _get_running_foreground_apps() -> set[str]:
    """Return names of all visible (foreground) apps via AppleScript.

    Used as a fallback when no tiling WM is available.
    """
    try:
        result = subprocess.run(
            [
                "osascript", "-e",
                "tell application \"System Events\" to return name of every process"
                " whose background only is false",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return set()
        return {name.strip() for name in result.stdout.split(",")}
    except (subprocess.SubprocessError, OSError):
        return set()


class WindowSnapshotPoller:
    """Tracks ANY application that opens during recording.

    Two modes:
    - **WM mode** (AeroSpace / yabai present): uses ``wm.list_windows()`` to
      detect new windows with their workspace labels.
    - **Fallback mode** (no WM): polls the macOS process list via AppleScript
      and records new foreground apps without workspace information.

    Apps already handled by richer adapters (Chrome, Safari, VS Code, iTerm2,
    etc.) are skipped in both modes to avoid duplicate events.
    """

    # OS-level app names handled by specific pollers — skip them here
    _MANAGED_OS_NAMES: frozenset[str] = frozenset({
        # Browsers (BrowserPoller)
        "Google Chrome", "Chromium", "Safari", "Arc",
        # IDEs (IDEPoller)
        "Code", "Cursor", "Zed",
        # Terminals (TerminalPoller)
        "iTerm2", "Terminal", "Warp", "kitty",
    })

    def __init__(
        self,
        actions: list[dict],
        poll_interval: float = 2.0,
        include_open: bool = False,
    ) -> None:
        self._actions = actions
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # WM mode state
        self._seen_ids: set[int] = set()
        self._wm: object | None = None
        # Fallback mode state
        self._seen_apps: set[str] = set()
        # Whether to record already-open apps on start
        self._include_open = include_open

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="window-snapshot-poller"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 1)

    def _run(self) -> None:
        self._wm = WorkspaceManagerRegistry().detect_active()

        if self._wm is not None:
            # WM mode — seed with currently open windows
            try:
                initial = self._wm.list_windows()
                self._seen_ids = {w.window_id for w in initial}
                
                if self._include_open:
                    # Record all currently open apps
                    for w in initial:
                        if w.app_name in self._MANAGED_OS_NAMES:
                            continue
                        action: dict = {
                            "type": "app_open",
                            "app_name": w.app_name,
                            "workspace": w.workspace,
                            "timestamp": _now_iso(),
                        }
                        self._actions.append(action)
                        logger.info("WindowSnapshotPoller: RECORDED app_open (baseline) app=%r workspace=%s", w.app_name, w.workspace)
            except Exception as exc:
                logger.warning("WindowSnapshotPoller: could not get initial window list: %s", exc)
            logger.info("WindowSnapshotPoller: WM mode (%s)", type(self._wm).__name__)
        else:
            # Fallback mode — seed with currently running apps
            self._seen_apps = _get_running_foreground_apps()
            
            if self._include_open:
                # Record all currently running apps
                for app_name in sorted(self._seen_apps):
                    if app_name in self._MANAGED_OS_NAMES:
                        continue
                    action: dict = {
                        "type": "app_open",
                        "app_name": app_name,
                        "timestamp": _now_iso(),
                    }
                    self._actions.append(action)
                    logger.info("WindowSnapshotPoller: RECORDED app_open (baseline) app=%r", app_name)
            
            logger.info("WindowSnapshotPoller: fallback mode (no WM detected)")

        while not self._stop_event.is_set():
            try:
                if self._wm is not None:
                    self._poll_wm()
                else:
                    self._poll_fallback()
            except Exception as exc:
                logger.warning("WindowSnapshotPoller: poll error: %s", exc)
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll_wm(self) -> None:
        """WM mode: detect new windows and record app + workspace."""
        windows = self._wm.list_windows()
        logger.debug("WindowSnapshotPoller: WM mode found %d windows", len(windows))
        for w in windows:
            if w.window_id in self._seen_ids:
                continue
            self._seen_ids.add(w.window_id)
            if w.app_name in self._MANAGED_OS_NAMES:
                logger.debug("WindowSnapshotPoller: skipping managed app %r", w.app_name)
                continue
            action: dict = {
                "type": "app_open",
                "app_name": w.app_name,
                "workspace": w.workspace,
                "timestamp": _now_iso(),
            }
            self._actions.append(action)
            logger.info("WindowSnapshotPoller: RECORDED app_open app=%r workspace=%s", w.app_name, w.workspace)

    def _poll_fallback(self) -> None:
        """Fallback mode: detect new foreground apps, no workspace info."""
        current = _get_running_foreground_apps()
        logger.debug("WindowSnapshotPoller: fallback mode found %d apps: %s", len(current), current)
        new_apps = current - self._seen_apps
        for app_name in sorted(new_apps):
            if app_name in self._MANAGED_OS_NAMES:
                logger.debug("WindowSnapshotPoller: skipping managed app %r", app_name)
                continue
            action: dict = {
                "type": "app_open",
                "app_name": app_name,
                "timestamp": _now_iso(),
            }
            self._actions.append(action)
            logger.info("WindowSnapshotPoller: RECORDED app_open (no WM) app=%r", app_name)
        self._seen_apps = current


class RecorderDaemon:
    """In-process Unix socket server that records workspace actions."""

    def __init__(self, workspace_name: str, db_path: Path, include_open: bool = False) -> None:
        self.workspace_name = workspace_name
        self.db_path = db_path
        self.include_open = include_open
        self._actions: list[dict] = []
        self._running = False
        self._sock: socket.socket | None = None
        self._workspace_id: int | None = None
        self._vpn_poller: VPNPoller | None = None
        self._browser_poller: BrowserPoller | None = None
        self._ide_poller: IDEPoller | None = None
        self._terminal_poller: TerminalPoller | None = None
        self._window_poller: WindowSnapshotPoller | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialise the store entry, write PID, and start the event loop."""
        _LOADOUT_DIR.mkdir(parents=True, exist_ok=True)

        # Write PID file
        _PID_PATH.write_text(str(os.getpid()))

        # Create workspace in the store
        store = WorkspaceStore(self.db_path)
        self._workspace_id = store.create_workspace(self.workspace_name)
        store.close()

        # Remove stale socket file
        if _SOCKET_PATH.exists():
            _SOCKET_PATH.unlink()

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(_SOCKET_PATH))
        self._sock.listen(5)
        self._sock.settimeout(1.0)  # allows periodic checks of self._running

        self._running = True

        # Handle SIGTERM for clean shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)

        # Start pollers (pass include_open flag)
        self._vpn_poller = VPNPoller(self._actions)
        self._vpn_poller.start()

        self._browser_poller = BrowserPoller(self._actions, include_open=self.include_open)
        self._browser_poller.start()

        self._ide_poller = IDEPoller(self._actions, include_open=self.include_open)
        self._ide_poller.start()

        self._terminal_poller = TerminalPoller(self._actions, include_open=self.include_open)
        self._terminal_poller.start()

        self._window_poller = WindowSnapshotPoller(self._actions, include_open=self.include_open)
        self._window_poller.start()

        self._loop()

    def _handle_signal(self, signum: int, frame: object) -> None:
        self._shutdown()

    def _loop(self) -> None:
        """Accept connections and process messages until stopped."""
        assert self._sock is not None
        while self._running:
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self._handle_connection(conn)
            finally:
                conn.close()

        self._cleanup()

    def _handle_connection(self, conn: socket.socket) -> None:
        """Read a JSON message from a connection and respond."""
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break

        if not data:
            return

        try:
            msg = json.loads(data.decode().strip())
        except json.JSONDecodeError:
            conn.sendall(b'{"status": "error", "reason": "invalid JSON"}\n')
            return

        command = msg.get("command")

        if command == "stop":
            action_count = self._flush_to_store()
            response = {
                "status": "ok",
                "workspace": self.workspace_name,
                "action_count": action_count,
            }
            conn.sendall((json.dumps(response) + "\n").encode())
            self._running = False

        elif command == "status":
            response = {
                "status": "ok",
                "workspace": self.workspace_name,
                "action_count": len(self._actions),
            }
            conn.sendall((json.dumps(response) + "\n").encode())

        elif command == "record_action":
            action = msg.get("action", {})
            self._actions.append(action)
            conn.sendall(b'{"status": "ok"}\n')

        else:
            conn.sendall(b'{"status": "error", "reason": "unknown command"}\n')

    # ------------------------------------------------------------------
    # Store flushing
    # ------------------------------------------------------------------

    def _flush_to_store(self) -> int:
        """Write accumulated actions to the store. Returns action count."""
        store = WorkspaceStore(self.db_path)
        try:
            if self._workspace_id is not None:
                store.save_actions(self._workspace_id, self._actions)
            return len(self._actions)
        finally:
            store.close()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _shutdown(self) -> None:
        self._running = False

    def _cleanup(self) -> None:
        # Stop all pollers
        if self._vpn_poller is not None:
            self._vpn_poller.stop()
        if self._browser_poller is not None:
            self._browser_poller.stop()
        if self._ide_poller is not None:
            self._ide_poller.stop()
        if self._terminal_poller is not None:
            self._terminal_poller.stop()
        if self._window_poller is not None:
            self._window_poller.stop()

        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        if _SOCKET_PATH.exists():
            _SOCKET_PATH.unlink(missing_ok=True)
        if _PID_PATH.exists():
            _PID_PATH.unlink(missing_ok=True)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ctx recorder daemon")
    parser.add_argument("workspace_name", help="Name of the workspace being recorded")
    parser.add_argument(
        "--db",
        default=str(_LOADOUT_DIR / "loadout.db"),
        help="Path to the SQLite database (default: ~/.loadout/loadout.db)",
    )
    parser.add_argument(
        "--include-open",
        action="store_true",
        default=False,
        help="Also capture apps/tabs/projects already open when recording starts",
    )
    return parser.parse_args()


if __name__ == "__main__":
    _setup_logging()
    logger.info("=" * 60)
    logger.info("loadout daemon starting")
    logger.info("=" * 60)
    args = _parse_args()
    logger.info("Workspace: %s", args.workspace_name)
    logger.info("Database: %s", args.db)
    logger.info("Include open: %s", args.include_open)
    logger.info("Log file: %s", _LOG_PATH)
    daemon = RecorderDaemon(
        workspace_name=args.workspace_name,
        db_path=Path(args.db),
        include_open=args.include_open,
    )
    daemon.start()
