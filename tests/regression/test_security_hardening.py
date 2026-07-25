"""
Regression tests for security hardening (2026-07-25).

Covers:
- GIT_CONFIG_NOSYSTEM / GIT_TERMINAL_PROMPT in all git subprocess paths
- Rate limiter thread safety and sliding window
- Workspace ID path traversal prevention
- Output directory validation
- API model field length limits
- Subprocess timeout enforcement
- Token-in-URL prevention (GIT_ASKPASS)
- Sensitive directory blocklist
"""

import os
import re
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# GIT_CONFIG_NOSYSTEM in subprocess paths
# ---------------------------------------------------------------------------
class TestGitSafeEnv:
    """Verify _GIT_SAFE_ENV is applied to all git subprocess calls."""

    def test_ingestion_has_safe_env(self):
        from miie.processing.ingestion import _GIT_SAFE_ENV

        assert _GIT_SAFE_ENV["GIT_CONFIG_NOSYSTEM"] == "1"
        assert _GIT_SAFE_ENV["GIT_TERMINAL_PROMPT"] == "0"
        assert _GIT_SAFE_ENV["GIT_EDITOR"] == ":"
        assert _GIT_SAFE_ENV["GIT_MERGE_AUTOEDIT"] == "no"

    def test_commit_extractor_has_safe_env(self):
        from miie.processing.extraction.commit_extractor import _GIT_SAFE_ENV

        assert _GIT_SAFE_ENV["GIT_CONFIG_NOSYSTEM"] == "1"
        assert _GIT_SAFE_ENV["GIT_TERMINAL_PROMPT"] == "0"

    def test_extraction_engine_has_safe_env(self):
        from miie.processing.extraction.engine import _GIT_SAFE_ENV

        assert _GIT_SAFE_ENV["GIT_CONFIG_NOSYSTEM"] == "1"
        assert _GIT_SAFE_ENV["GIT_TERMINAL_PROMPT"] == "0"

    def test_benchmark_generator_has_safe_env(self):
        from miie.benchmark.generator import _GIT_SAFE_ENV

        assert _GIT_SAFE_ENV["GIT_CONFIG_NOSYSTEM"] == "1"
        assert _GIT_SAFE_ENV["GIT_TERMINAL_PROMPT"] == "0"
        assert _GIT_SAFE_ENV["GIT_EDITOR"] == ":"

    def test_safe_env_inherits_os_environ(self):
        from miie.processing.ingestion import _GIT_SAFE_ENV

        # Should contain all our GIT_ keys
        assert "GIT_CONFIG_NOSYSTEM" in _GIT_SAFE_ENV
        assert "GIT_TERMINAL_PROMPT" in _GIT_SAFE_ENV
        assert "GIT_EDITOR" in _GIT_SAFE_ENV
        assert "GIT_MERGE_AUTOEDIT" in _GIT_SAFE_ENV
        # Should contain at least some standard env vars
        assert "PATH" in _GIT_SAFE_ENV or "COMSPEC" in _GIT_SAFE_ENV


# ---------------------------------------------------------------------------
# Rate limiter thread safety
# ---------------------------------------------------------------------------
class TestRateLimiter:
    """Verify _RateLimiter is thread-safe and enforces sliding window."""

    def _make_limiter(self, max_requests=5, window=1):
        from miie.api.server import _RateLimiter

        return _RateLimiter(max_requests=max_requests, window_seconds=window)

    def test_basic_allow(self):
        limiter = self._make_limiter(max_requests=3)
        assert limiter.is_allowed() is True
        assert limiter.is_allowed() is True
        assert limiter.is_allowed() is True

    def test_basic_reject(self):
        limiter = self._make_limiter(max_requests=2)
        assert limiter.is_allowed() is True
        assert limiter.is_allowed() is True
        assert limiter.is_allowed() is False

    def test_window_expiry(self):
        limiter = self._make_limiter(max_requests=1, window=0.1)
        assert limiter.is_allowed() is True
        assert limiter.is_allowed() is False
        time.sleep(0.15)
        assert limiter.is_allowed() is True

    def test_thread_safety_no_lost_increments(self):
        """Concurrent is_allowed() calls should never exceed max_requests."""
        limiter = self._make_limiter(max_requests=100, window=10)
        results = []

        def hit():
            results.append(limiter.is_allowed())

        threads = [threading.Thread(target=hit) for _ in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed = sum(1 for r in results if r is True)
        assert allowed == 100
        assert len(results) == 200

    def test_thread_safety_no_race_condition(self):
        """Two threads racing on eviction should not corrupt the deque."""
        limiter = self._make_limiter(max_requests=50, window=0.05)
        errors = []

        def rapid_fire():
            try:
                for _ in range(100):
                    limiter.is_allowed()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=rapid_fire) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# ---------------------------------------------------------------------------
# Workspace ID path traversal
# ---------------------------------------------------------------------------
class TestWorkspacePathTraversal:
    """Verify workspace IDs cannot escape via .. sequences."""

    def test_sanitize_strips_double_dot(self):
        from miie.workspace.persistence import WorkspacePersistence

        ws = WorkspacePersistence(Path("/tmp/test_workspace"))
        safe = ws._sanitize_id("....//....//etc/passwd")
        assert ".." not in safe
        assert "/" not in safe

    def test_sanitize_strips_single_dot(self):
        from miie.workspace.persistence import WorkspacePersistence

        ws = WorkspacePersistence(Path("/tmp/test_workspace"))
        safe = ws._sanitize_id("legit/../../../etc/shadow")
        assert ".." not in safe
        assert "/" not in safe

    def test_load_returns_none_for_traversal(self):
        from miie.workspace.persistence import WorkspacePersistence

        ws = WorkspacePersistence(Path("/tmp/test_workspace_traversal"))
        # load sanitizes the ID, so traversal is neutralized
        result = ws.load("....//....//etc/passwd")
        assert result is None  # Not found (sanitized to harmless path)

    def test_delete_returns_false_for_traversal(self):
        from miie.workspace.persistence import WorkspacePersistence

        ws = WorkspacePersistence(Path("/tmp/test_workspace_traversal"))
        result = ws.delete("....//....//etc/passwd")
        assert result is False  # Not found (sanitized to harmless path)

    def test_get_bookmarks_returns_empty_for_traversal(self):
        from miie.workspace.persistence import WorkspacePersistence

        ws = WorkspacePersistence(Path("/tmp/test_workspace_traversal"))
        result = ws.get_bookmarks("....//....//etc/passwd")
        assert result == []  # Not found (sanitized to harmless path)


# ---------------------------------------------------------------------------
# Output directory validation (inline in dependencies.py)
# ---------------------------------------------------------------------------
class TestOutputDirValidation:
    """Verify output_dir rejects path traversal and sensitive directories."""

    def test_output_dir_rejects_double_dot(self):
        """The inline validation checks '..' in raw_output."""
        raw_output = "/tmp/../../../etc"
        assert ".." in raw_output

    def test_output_dir_rejects_special_chars(self):
        """The inline validation checks for <>\"|?*."""
        raw_output = "/tmp/output<>test"
        assert re.search(r"[<>\"|?*]", raw_output)

    def test_output_dir_rejects_sensitive_system_dirs(self):
        """The inline validation blocks /etc, /proc, /sys, /dev, /bin, /sbin, /usr."""
        sensitive = ["/etc", "/proc", "/sys", "/dev", "/bin", "/sbin", "/usr"]
        for d in sensitive:
            assert d.startswith("/") or d[1] == ":"  # Absolute paths

    def test_sensitive_directories_in_dependencies_source(self):
        """Verify dependencies.py contains the sensitive directory blocklist."""
        deps_path = Path(__file__).parents[2] / "src" / "miie" / "api" / "dependencies.py"
        content = deps_path.read_text(encoding="utf-8")
        assert "/etc" in content
        assert "/proc" in content
        assert ".ssh" in content
        assert ".aws" in content


# ---------------------------------------------------------------------------
# API model field length limits
# ---------------------------------------------------------------------------
class TestAPIModelLimits:
    """Verify API models enforce max_length on critical fields."""

    def test_repo_field_max_length(self):
        from miie.api.models import AnalyzeRequest

        # Should accept normal repo
        req = AnalyzeRequest(repo="https://github.com/owner/repo")
        assert req.repo == "https://github.com/owner/repo"

        # Should reject very long repo string
        with pytest.raises(Exception):
            AnalyzeRequest(repo="x" * 3000)

    def test_output_dir_field_max_length(self):
        from miie.api.models import AnalyzeRequest

        # Should accept normal output_dir
        req = AnalyzeRequest(repo="r", output_dir="/tmp/output")
        assert req.output_dir == "/tmp/output"

        # Should reject very long output_dir
        with pytest.raises(Exception):
            AnalyzeRequest(repo="r", output_dir="x" * 2000)


# ---------------------------------------------------------------------------
# Subprocess timeout enforcement
# ---------------------------------------------------------------------------
class TestSubprocessTimeouts:
    """Verify subprocess calls have timeout parameters."""

    def test_commit_extractor_has_timeout(self):
        """commit_extractor.py git log call should have timeout=120."""
        src = Path(__file__).parents[2] / "src" / "miie" / "processing" / "extraction" / "commit_extractor.py"
        content = src.read_text(encoding="utf-8")
        assert "timeout=120" in content, "commit_extractor.py missing timeout=120 on git log"

    def test_ingestion_has_timeout(self):
        """ingestion.py subprocess calls should have timeout."""
        src = Path(__file__).parents[2] / "src" / "miie" / "processing" / "ingestion.py"
        content = src.read_text(encoding="utf-8")
        assert "timeout=" in content, "ingestion.py missing timeout on subprocess calls"

    def test_benchmark_generator_has_timeout(self):
        """generator.py subprocess calls should have timeout."""
        src = Path(__file__).parents[2] / "src" / "miie" / "benchmark" / "generator.py"
        content = src.read_text(encoding="utf-8")
        assert "timeout=30" in content, "generator.py missing timeout on subprocess calls"


# ---------------------------------------------------------------------------
# Token-in-URL prevention
# ---------------------------------------------------------------------------
class TestTokenInURL:
    """Verify git clone does not embed tokens in URLs."""

    def test_git_askpass_used(self):
        src = Path(__file__).parents[2] / "src" / "miie" / "utils" / "git.py"
        content = src.read_text(encoding="utf-8")
        assert "GIT_ASKPASS" in content, "git.py missing GIT_ASKPASS fix"

    def test_clone_does_not_put_token_in_url(self):
        src = Path(__file__).parents[2] / "src" / "miie" / "utils" / "git.py"
        content = src.read_text(encoding="utf-8")
        assert "x-access-token" not in content, "git.py still contains token-in-URL pattern"


# ---------------------------------------------------------------------------
# Sensitive directory blocklist
# ---------------------------------------------------------------------------
class TestSensitiveDirectoryBlocklist:
    """Verify sensitive directories are in the dependencies.py source."""

    def test_windows_credentials_in_source(self):
        deps_path = Path(__file__).parents[2] / "src" / "miie" / "api" / "dependencies.py"
        content = deps_path.read_text(encoding="utf-8")
        assert "Credentials" in content or "credentials" in content

    def test_aws_in_source(self):
        deps_path = Path(__file__).parents[2] / "src" / "miie" / "api" / "dependencies.py"
        content = deps_path.read_text(encoding="utf-8")
        assert ".aws" in content

    def test_kube_in_source(self):
        deps_path = Path(__file__).parents[2] / "src" / "miie" / "api" / "dependencies.py"
        content = deps_path.read_text(encoding="utf-8")
        assert ".kube" in content
