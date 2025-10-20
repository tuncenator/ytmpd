"""Basic tests for ytmpctl CLI client.

These tests verify basic functionality without complex mocking.
Full integration tests are in Phase 8.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


YTMPCTL = Path(__file__).parent.parent / "bin" / "ytmpctl"


class TestYtmpctlBasic:
    """Basic sanity tests for ytmpctl."""

    def test_ytmpctl_exists(self):
        """Test ytmpctl file exists and is executable."""
        assert YTMPCTL.exists()
        assert YTMPCTL.stat().st_mode & 0o111  # Has execute permission

    def test_ytmpctl_help(self):
        """Test ytmpctl help command runs successfully."""
        result = subprocess.run(
            [str(YTMPCTL), "help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "ytmpctl" in result.stdout
        assert "sync" in result.stdout
        assert "status" in result.stdout
        assert "list-playlists" in result.stdout
        assert "mpc" in result.stdout

    def test_ytmpctl_no_args_shows_help(self):
        """Test ytmpctl with no args shows help."""
        result = subprocess.run(
            [str(YTMPCTL)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "ytmpctl" in result.stdout

    def test_ytmpctl_unknown_command(self):
        """Test ytmpctl with unknown command fails appropriately."""
        result = subprocess.run(
            [str(YTMPCTL), "nonexistent_command"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Unknown command" in result.stderr

    def test_ytmpctl_sync_daemon_not_running(self):
        """Test ytmpctl sync fails gracefully when daemon not running."""
        # This assumes daemon is NOT running - if it is, test will fail
        # but that's okay since the test is for the error message
        result = subprocess.run(
            [str(YTMPCTL), "sync"],
            capture_output=True,
            text=True,
        )
        # Either succeeds (daemon running) or shows helpful error
        if result.returncode != 0:
            assert "daemon" in result.stderr.lower() or "socket" in result.stderr.lower()

    def test_ytmpctl_status_daemon_not_running(self):
        """Test ytmpctl status fails gracefully when daemon not running."""
        result = subprocess.run(
            [str(YTMPCTL), "status"],
            capture_output=True,
            text=True,
        )
        # Either succeeds (daemon running) or shows helpful error
        if result.returncode != 0:
            assert "daemon" in result.stderr.lower() or "socket" in result.stderr.lower()

    def test_ytmpctl_list_daemon_not_running(self):
        """Test ytmpctl list fails gracefully when daemon not running."""
        result = subprocess.run(
            [str(YTMPCTL), "list-playlists"],
            capture_output=True,
            text=True,
        )
        # Either succeeds (daemon running) or shows helpful error
        if result.returncode != 0:
            assert "daemon" in result.stderr.lower() or "socket" in result.stderr.lower()


class TestYtmpctlPythonSyntax:
    """Test that ytmpctl has valid Python syntax."""

    def test_ytmpctl_python_syntax(self):
        """Test ytmpctl is valid Python code."""
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(YTMPCTL)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in ytmpctl: {result.stderr}"


class TestYtmpctlSearch:
    """Tests for ytmpctl search command functionality."""

    def test_search_help_includes_command(self):
        """Test that help message includes search command."""
        result = subprocess.run(
            [str(YTMPCTL), "help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "search" in result.stdout.lower()
        assert "interactive" in result.stdout.lower() or "youtube music" in result.stdout.lower()

    def test_search_command_requires_daemon(self):
        """Test that search command handles daemon not running gracefully."""
        # Provide empty input to exit immediately
        result = subprocess.run(
            [str(YTMPCTL), "search"],
            capture_output=True,
            text=True,
            input="\n",  # Empty query to exit
        )
        # Should either work (daemon running) or show daemon error
        # Empty query should exit with code 0
        if result.returncode != 0:
            # If daemon not running, should show helpful error
            assert "daemon" in result.stderr.lower() or "socket" in result.stderr.lower()
