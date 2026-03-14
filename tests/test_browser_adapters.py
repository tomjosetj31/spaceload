"""Unit tests for browser adapters (mocked subprocess calls)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from loadout.adapters.browser.base import BrowserAdapter, TabSet
from loadout.adapters.browser.chrome import ChromeAdapter
from loadout.adapters.browser.safari import SafariAdapter
from loadout.adapters.browser.arc import ArcAdapter
from loadout.adapters.browser.firefox import FirefoxAdapter
from loadout.adapters.browser.registry import BrowserAdapterRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completed_process(stdout="", returncode=0):
    mock = MagicMock()
    mock.stdout = stdout
    mock.returncode = returncode
    return mock


# ---------------------------------------------------------------------------
# ChromeAdapter
# ---------------------------------------------------------------------------

class TestChromeAdapter:
    def setup_method(self):
        self.adapter = ChromeAdapter()

    def test_name(self):
        assert self.adapter.name == "chrome"

    def test_is_available_when_running(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            assert self.adapter.is_available() is True

    def test_is_available_when_not_running(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            assert self.adapter.is_available() is False

    def test_get_open_tabs_returns_urls(self):
        output = "https://github.com\nhttps://example.com\n"
        with patch("subprocess.run", return_value=_make_completed_process(stdout=output)):
            tabs = self.adapter.get_open_tabs()
        assert tabs == ["https://github.com", "https://example.com"]

    def test_get_open_tabs_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            assert self.adapter.get_open_tabs() == []

    def test_get_open_tabs_returns_empty_on_blank_output(self):
        with patch("subprocess.run", return_value=_make_completed_process(stdout="")):
            assert self.adapter.get_open_tabs() == []

    def test_open_url_success(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)) as mock_run:
            result = self.adapter.open_url("https://example.com")
        assert result is True
        args = mock_run.call_args[0][0]
        assert "Google Chrome" in args
        assert "https://example.com" in args

    def test_open_url_failure(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            assert self.adapter.open_url("https://example.com") is False


# ---------------------------------------------------------------------------
# SafariAdapter
# ---------------------------------------------------------------------------

class TestSafariAdapter:
    def setup_method(self):
        self.adapter = SafariAdapter()

    def test_name(self):
        assert self.adapter.name == "safari"

    def test_is_available_when_running(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            assert self.adapter.is_available() is True

    def test_is_available_when_not_running(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            assert self.adapter.is_available() is False

    def test_get_open_tabs_returns_urls(self):
        output = "https://apple.com\nhttps://duckduckgo.com\n"
        with patch("subprocess.run", return_value=_make_completed_process(stdout=output)):
            tabs = self.adapter.get_open_tabs()
        assert tabs == ["https://apple.com", "https://duckduckgo.com"]

    def test_get_open_tabs_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            assert self.adapter.get_open_tabs() == []

    def test_open_url_success(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)) as mock_run:
            result = self.adapter.open_url("https://apple.com")
        assert result is True
        args = mock_run.call_args[0][0]
        assert "Safari" in args

    def test_open_url_failure(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            assert self.adapter.open_url("https://apple.com") is False


# ---------------------------------------------------------------------------
# ArcAdapter
# ---------------------------------------------------------------------------

class TestArcAdapter:
    def setup_method(self):
        self.adapter = ArcAdapter()

    def test_name(self):
        assert self.adapter.name == "arc"

    def test_is_available_when_running(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            assert self.adapter.is_available() is True

    def test_is_available_when_not_running(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            assert self.adapter.is_available() is False

    def test_get_open_tabs_returns_urls(self):
        output = "https://arc.net\nhttps://linear.app\n"
        with patch("subprocess.run", return_value=_make_completed_process(stdout=output)):
            tabs = self.adapter.get_open_tabs()
        assert tabs == ["https://arc.net", "https://linear.app"]

    def test_get_open_tabs_filters_blank_lines(self):
        output = "https://arc.net\n\n\nhttps://linear.app\n"
        with patch("subprocess.run", return_value=_make_completed_process(stdout=output)):
            tabs = self.adapter.get_open_tabs()
        assert tabs == ["https://arc.net", "https://linear.app"]

    def test_open_url_success(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)) as mock_run:
            result = self.adapter.open_url("https://arc.net")
        assert result is True
        args = mock_run.call_args[0][0]
        assert "Arc" in args

    def test_open_url_failure(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            assert self.adapter.open_url("https://arc.net") is False


# ---------------------------------------------------------------------------
# BrowserAdapterRegistry
# ---------------------------------------------------------------------------

class TestBrowserAdapterRegistry:
    def test_available_adapters_returns_running_browsers(self):
        registry = BrowserAdapterRegistry()
        mock_chrome = MagicMock()
        mock_chrome.is_available.return_value = True
        mock_safari = MagicMock()
        mock_safari.is_available.return_value = False
        registry._adapters = [mock_chrome, mock_safari]

        result = registry.available_adapters()
        assert result == [mock_chrome]

    def test_available_adapters_empty_when_none_running(self):
        registry = BrowserAdapterRegistry()
        for adapter in registry._adapters:
            adapter.is_available = lambda: False

        with patch.object(ChromeAdapter, "is_available", return_value=False), \
             patch.object(SafariAdapter, "is_available", return_value=False), \
             patch.object(ArcAdapter, "is_available", return_value=False):
            assert registry.available_adapters() == []

    def test_get_adapter_by_name(self):
        registry = BrowserAdapterRegistry()
        adapter = registry.get_adapter("chrome")
        assert adapter is not None
        assert adapter.name == "chrome"

    def test_get_adapter_safari(self):
        registry = BrowserAdapterRegistry()
        assert registry.get_adapter("safari").name == "safari"

    def test_get_adapter_arc(self):
        registry = BrowserAdapterRegistry()
        assert registry.get_adapter("arc").name == "arc"

    def test_get_adapter_firefox(self):
        registry = BrowserAdapterRegistry()
        assert registry.get_adapter("firefox").name == "firefox"

    def test_get_adapter_unknown_returns_none(self):
        registry = BrowserAdapterRegistry()
        assert registry.get_adapter("opera") is None


# ---------------------------------------------------------------------------
# FirefoxAdapter
# ---------------------------------------------------------------------------

class TestFirefoxAdapter:
    def setup_method(self):
        self.adapter = FirefoxAdapter()

    def test_name(self):
        assert self.adapter.name == "firefox"

    def test_is_available_when_running(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
            assert self.adapter.is_available() is True

    def test_is_available_when_not_running(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            assert self.adapter.is_available() is False

    def test_get_open_tabs_returns_empty_when_no_profile(self):
        adapter = FirefoxAdapter()
        adapter._profile_dir = None
        assert adapter.get_open_tabs() == []

    def test_open_url_success(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=0)) as mock_run:
            result = self.adapter.open_url("https://mozilla.org")
        assert result is True
        args = mock_run.call_args[0][0]
        assert "Firefox" in args
        assert "https://mozilla.org" in args

    def test_open_url_failure(self):
        with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
            assert self.adapter.open_url("https://mozilla.org") is False


# ---------------------------------------------------------------------------
# TabSet dataclass
# ---------------------------------------------------------------------------

class TestTabSet:
    def test_default_urls_empty(self):
        ts = TabSet(browser="chrome")
        assert ts.urls == []

    def test_with_urls(self):
        ts = TabSet(browser="safari", urls=["https://a.com", "https://b.com"])
        assert len(ts.urls) == 2
