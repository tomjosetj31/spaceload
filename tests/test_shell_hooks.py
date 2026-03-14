"""Tests for shell integration hooks."""

from __future__ import annotations

import pytest

from ctx.shell.hooks import get_hook_script, ZSH_HOOK, BASH_HOOK


class TestGetHookScript:
    def test_zsh_hook(self):
        script = get_hook_script("zsh")
        assert script == ZSH_HOOK
        assert "_ctx_preexec" in script
        assert "add-zsh-hook preexec" in script
        assert "nc -U" in script  # Uses netcat for Unix socket
    
    def test_zsh_case_insensitive(self):
        assert get_hook_script("ZSH") == ZSH_HOOK
        assert get_hook_script("Zsh") == ZSH_HOOK
    
    def test_bash_hook(self):
        script = get_hook_script("bash")
        assert script == BASH_HOOK
        assert "_ctx_debug_trap" in script
        assert 'trap' in script
        assert "nc -U" in script
    
    def test_bash_case_insensitive(self):
        assert get_hook_script("BASH") == BASH_HOOK
        assert get_hook_script("Bash") == BASH_HOOK
    
    def test_unsupported_shell(self):
        with pytest.raises(ValueError, match="Unsupported shell"):
            get_hook_script("fish")
        
        with pytest.raises(ValueError, match="Unsupported shell"):
            get_hook_script("powershell")


class TestZshHookContent:
    def test_checks_socket_exists(self):
        assert '[[ -S "$_ctx_socket" ]]' in ZSH_HOOK
    
    def test_captures_tty(self):
        assert "tty" in ZSH_HOOK
    
    def test_captures_directory(self):
        assert "pwd" in ZSH_HOOK
    
    def test_sends_json_to_daemon(self):
        assert '"command":"record_action"' in ZSH_HOOK
        assert '"type":"terminal_command"' in ZSH_HOOK
    
    def test_runs_in_background(self):
        # zsh uses &! for disowned background jobs
        assert "&!" in ZSH_HOOK


class TestBashHookContent:
    def test_checks_socket_exists(self):
        assert '[[ -S "$_ctx_socket" ]]' in BASH_HOOK
    
    def test_captures_tty(self):
        assert "tty" in BASH_HOOK
    
    def test_captures_directory(self):
        assert "pwd" in BASH_HOOK
    
    def test_sends_json_to_daemon(self):
        assert '"command":"record_action"' in BASH_HOOK
        assert '"type":"terminal_command"' in BASH_HOOK
    
    def test_runs_in_background(self):
        # bash uses & for background jobs
        assert "} &" in BASH_HOOK
