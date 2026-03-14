# Contributing to Loadout

Thank you for your interest in contributing to `loadout`! This document covers everything you need to get started.

## Table of Contents

- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [How to Contribute](#how-to-contribute)
- [Adding a New Adapter](#adding-a-new-adapter)
- [Code Style](#code-style)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Issues](#reporting-issues)

---

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:

   ```bash
   git clone https://github.com/tomjosetj31/loadout
   cd loadout
   ```

3. Add the upstream remote so you can pull in future changes:

   ```bash
   git remote add upstream https://github.com/tomjosetj31/loadout
   ```

---

## Project Structure

```
loadout/
├── loadout/
│   ├── adapters/       # Per-integration plugins (browser, VPN, IDE, terminal)
│   ├── cli/            # Click-based command interface
│   ├── daemon/         # Unix socket server that records actions in the background
│   ├── replayer/       # Replays recorded action sequences
│   ├── shell/          # Shell hook support (zsh, bash)
│   └── store/          # SQLite-backed persistence layer with YAML export/import
├── tests/              # Test suite
├── pyproject.toml      # Project metadata and dependencies
└── README.md
```

---

## Development Setup

Requires **Python 3.11+**.

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install the package in editable mode with dev dependencies
pip install -e ".[dev]"

# Optional: install Firefox support
pip install -e ".[firefox]"
```

> If there is no `dev` extras group yet, install test dependencies directly:
> ```bash
> pip install pytest
> ```

---

## Running Tests

```bash
pytest
```

Run a specific test file:

```bash
pytest tests/test_adapters.py
```

Run with verbose output:

```bash
pytest -v
```

All tests must pass before a pull request can be merged.

---

## How to Contribute

### Bug fixes

1. Open an issue describing the bug (or find an existing one).
2. Create a branch: `git checkout -b fix/short-description`.
3. Fix the bug and add a regression test if possible.
4. Submit a pull request referencing the issue.

### New features

1. Open an issue to discuss the feature before writing code — this avoids wasted effort.
2. Create a branch: `git checkout -b feature/short-description`.
3. Implement the feature and add tests.
4. Update `README.md` if user-facing behaviour changes.
5. Submit a pull request.

### Documentation improvements

Documentation fixes and clarifications are always welcome. Edit the relevant `.md` file and open a pull request.

---

## Adding a New Adapter

Adapters live in `loadout/adapters/` and teach `loadout` how to record and replay a specific integration (browser, VPN, IDE, terminal app, etc.).

1. Create a new file: `loadout/adapters/<name>_adapter.py`.
2. Implement the adapter class — follow the pattern of an existing adapter (e.g. `chrome_adapter.py`) as a reference.
3. Register the adapter in `loadout/adapters/__init__.py` (or wherever adapters are loaded).
4. Add tests under `tests/` covering at minimum record and replay paths.
5. Document the new integration in `README.md` under **Supported Integrations**.

---

## Code Style

- Follow **PEP 8**.
- Use descriptive variable and function names.
- Keep functions small and focused.
- Add docstrings to public classes and functions.
- Avoid adding dependencies unless strictly necessary — prefer the standard library.

You can check formatting with:

```bash
# If ruff is available
ruff check .
ruff format --check .
```

---

## Submitting a Pull Request

1. Ensure all tests pass locally (`pytest`).
2. Keep commits focused — one logical change per commit.
3. Write a clear PR description:
   - **What** the change does.
   - **Why** it is needed.
   - Any **related issues** (use `Closes #<issue>` to auto-close).
4. Open the pull request against the `master` branch.
5. Be responsive to review feedback.

---

## Reporting Issues

Use [GitHub Issues](https://github.com/tomjosetj31/loadout/issues) to report bugs or request features.

When reporting a bug please include:

- macOS version.
- Python version (`python --version`).
- Steps to reproduce.
- Expected behaviour vs. actual behaviour.
- Relevant log output from `~/.loadout/daemon.log` or `~/.loadout/replay.log`.

---

Thank you for helping make `loadout` better!
