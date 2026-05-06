# Adapter Contracts

Spaceload uses a plugin-style adapter system. Each integration category (browser,
VPN, IDE, terminal, window manager) defines an abstract base class. Concrete
adapters subclass it. A registry discovers which adapters are available at runtime
by calling `is_available()` on each.

---

## How Registries Work

Every category has a registry class (e.g. `BrowserAdapterRegistry`). The registry:
1. Instantiates all known adapters at construction time.
2. Exposes `available_adapters()` → returns only those where `is_available()` is True.
3. Exposes `get_adapter(name)` → returns the adapter matching that name, or None.

The daemon's pollers call `available_adapters()` on each poll cycle. The replayer
calls `get_adapter(name)` to find the right adapter for a recorded action.

---

## Browser Adapter (`BrowserAdapter`)

**Base class:** `spaceload/adapters/browser/base.py`
**Implementations:** `chrome.py`, `safari.py`, `arc.py`, `firefox.py`
**Registry:** `spaceload/adapters/browser/registry.py`

| Method | Signature | What it must do |
|--------|-----------|-----------------|
| `name` | `@property → str` | Return a unique lowercase identifier, e.g. `"chrome"`. Used as the `browser` field in `browser_tab_open` actions. |
| `is_available()` | `() → bool` | Return True if this browser is currently running (not just installed). |
| `get_open_tabs()` | `() → list[str]` | Return the full URLs of all currently open tabs. Return `[]` if none or on error. |
| `open_url(url)` | `(str) → bool` | Open the given URL in this browser. Return True on success, False on failure. |

**Minimal stub:**
```python
from spaceload.adapters.browser.base import BrowserAdapter

class MyBrowserAdapter(BrowserAdapter):
    @property
    def name(self) -> str:
        return "mybrowser"

    def is_available(self) -> bool:
        # Check if the app process is running
        ...

    def get_open_tabs(self) -> list[str]:
        # Return list of open tab URLs via AppleScript or other mechanism
        ...

    def open_url(self, url: str) -> bool:
        # Open the URL; return True on success
        ...
```

Register by adding an instance to the `_adapters` list in `BrowserAdapterRegistry.__init__`.

---

## VPN Adapter (`VPNAdapter`)

**Base class:** `spaceload/adapters/vpn/base.py`
**Implementations:** `tailscale.py`, `wireguard.py`, `cisco.py`, `mullvad.py`, `openvpn.py`, `tunnelblick.py`
**Registry:** `spaceload/adapters/vpn/registry.py`

| Method | Signature | What it must do |
|--------|-----------|-----------------|
| `name` | class attribute `str` | Unique lowercase identifier, e.g. `"tailscale"`. Matches the `client` field in VPN actions. |
| `is_available()` | `() → bool` | Return True if the VPN client binary exists on PATH. |
| `detect()` | `() → VPNState \| None` | Return a `VPNState(connected, profile, client)` if the client is installed/running, else None. |
| `connect(config)` | `(dict) → bool` | Connect using the given config dict (the full action dict). Return True on success. |
| `disconnect()` | `() → bool` | Disconnect. Return True on success. |
| `get_config()` | `() → dict` | Return a dict snapshot of current config for replay use. |

**`VPNState` dataclass** (from `base.py`):
```python
@dataclass
class VPNState:
    connected: bool
    profile: str | None = None
    client: str = ""
```

**Registry note:** `VPNAdapterRegistry.detect_active()` iterates all adapters, calls
`detect()`, and returns the first `(adapter, VPNState)` pair where `state.connected`
is True — or None if no VPN is active.

---

## IDE Adapter (`IDEAdapter`)

**Base class:** `spaceload/adapters/ide/base.py`
**Implementations:** `vscode.py`, `cursor.py`, `zed.py`
**Registry:** `spaceload/adapters/ide/registry.py`

| Method | Signature | What it must do |
|--------|-----------|-----------------|
| `name` | `@property → str` | Unique lowercase identifier, e.g. `"vscode"`. Matches the `client` field in `ide_project_open` actions. |
| `is_available()` | `() → bool` | Return True if the IDE binary is present on PATH. |
| `get_open_projects()` | `() → list[str]` | Return absolute paths of all currently open projects/folders. |
| `open_project(path)` | `(str) → bool` | Open the path in this IDE. Return True on success. |

---

## Terminal Adapter (`TerminalAdapter`)

**Base class:** `spaceload/adapters/terminal/base.py`
**Implementations:** `iterm2.py`, `terminal_app.py`, `warp.py`, `kitty.py`
**Registry:** `spaceload/adapters/terminal/registry.py`

| Method | Signature | What it must do |
|--------|-----------|-----------------|
| `name` | `@property → str` | Unique lowercase identifier, e.g. `"iterm2"`. Matches the `app` field in terminal actions. |
| `is_available()` | `() → bool` | Return True if this terminal app is currently running. |
| `get_open_dirs()` | `() → list[str]` | Return working directories of all open terminal sessions. |
| `get_sessions()` | `() → list[TerminalSession]` | Return sessions with `session_id`. Default implementation wraps `get_open_dirs()` — override for accurate session tracking. |
| `open_in_dir(directory)` | `(str) → bool` | Open a new terminal session in the given directory. Return True on success. |

**`TerminalSession` dataclass** (from `base.py`):
```python
@dataclass
class TerminalSession:
    app: str
    directory: str
    session_id: str = ""  # e.g. tty path "/dev/ttys004"
```

**Optional method:** `open_with_commands(directory, commands)` — opens a terminal in
`directory` and sends each command in `commands` to the session. Used by the replayer
when consolidating terminal actions. Fall back to `open_in_dir` if not implemented.

---

## Window Manager Adapter (`WorkspaceManagerAdapter`)

**Base class:** `spaceload/adapters/wm/base.py`
**Implementations:** `aerospace.py`, `yabai.py`
**Registry:** `spaceload/adapters/wm/registry.py`

Used optionally — only when a supported tiling WM is running. Enables workspace
placement during replay.

| Method | Signature | What it must do |
|--------|-----------|-----------------|
| `name` | `@property → str` | Unique lowercase identifier, e.g. `"aerospace"`. |
| `is_available()` | `() → bool` | Return True if the WM binary is on PATH and the WM is running. |
| `list_windows()` | `() → list[WMWindow]` | Return all managed windows with their current workspace assignment. |
| `move_window_to_workspace(window_id, workspace)` | `(int, str) → bool` | Move the given window to the given workspace. Return True on success. |

**`WMWindow` dataclass** (from `base.py`):
```python
@dataclass
class WMWindow:
    window_id: int
    workspace: str   # workspace label as a string, e.g. "1", "browser"
    app_name: str    # macOS app name, e.g. "Google Chrome"
```

**Convenience methods** (implemented on the base class, no need to override):
- `get_app_workspace(app_name)` → workspace of first window belonging to the app
- `get_app_window_ids(app_name)` → list of window IDs for the app
- `move_app_to_workspace(app_name, workspace)` → moves the app's first window
