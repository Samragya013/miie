"""Git URL parser and cloner for MIIE.

Parses GitHub URLs, validates ownership, and clones repositories with auth support.
Windows-only: subprocess timeouts, disk cleanup, network retry.
"""

import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Git subprocess timeout (seconds)
GIT_TIMEOUT = 60

# Network retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 3, 8]

# GitHub URL patterns
GITHUB_URL_PATTERNS = [
    r"^https?://github\.com/([^/]+/[^/]+)(?:\.git)?$",
    r"^git@github\.com:([^/]+/[^/]+)\.git$",
    r"^ssh://git@github\.com/([^/]+/[^/]+)\.git$",
]


class GitURLParser:
    """Parse and validate GitHub repository URLs."""

    @staticmethod
    def parse(url: str) -> Tuple[str, str]:
        """Parse GitHub URL and return (owner, repo).

        Args:
            url: GitHub repository URL

        Returns:
            Tuple of (owner, repo)

        Raises:
            ValueError: If URL is invalid or not a GitHub URL
        """
        url = url.strip()

        # Handle SSH URLs (git@github.com:owner/repo.git)
        if url.startswith("git@github.com:"):
            url = "https://" + url.replace("git@github.com:", "github.com/")

        # Handle ssh://git@github.com/ URLs
        if url.startswith("ssh://git@github.com/"):
            url = "https://" + url[len("ssh://git@") :]

        # Handle git:// URLs
        if url.startswith("git://"):
            url = url.replace("git://", "https://")

        parsed = urlparse(url)
        # Only allow http/https schemes
        if parsed.scheme not in ("http", "https", ""):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme} — {url}")

        if parsed.netloc not in ("github.com", "www.github.com"):
            raise ValueError(f"Not a GitHub URL: {url}")

        path = parsed.path.strip("/")
        if not path:
            raise ValueError(f"Invalid GitHub URL (no path): {url}")

        # Remove .git suffix if present
        if path.endswith(".git"):
            path = path[:-4]

        parts = path.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid GitHub URL path: {path}")

        owner, repo = parts
        if not owner or not repo:
            raise ValueError(f"Invalid owner or repo in URL: {url}")

        return owner, repo

    @staticmethod
    def is_github_url(url: str) -> bool:
        """Check if URL is a GitHub repository URL."""
        try:
            GitURLParser.parse(url)
            return True
        except ValueError:
            return False


class GitCloner:
    """Clone Git repositories with auth support, timeout, retry, and cleanup."""

    def __init__(self, auth_token: Optional[str] = None, shallow_depth: int = 1):
        """Initialize Git cloner.

        Args:
            auth_token: GitHub personal access token for private repos
            shallow_depth: Depth for shallow clone (default: 1)
        """
        self.auth_token = auth_token
        self.shallow_depth = shallow_depth

    def clone(
        self,
        url: str,
        target_dir: Optional[Path] = None,
        cleanup_after: bool = False,
        on_progress=None,
    ) -> Path:
        """Clone a GitHub repository with timeout and retry.

        Args:
            url: GitHub repository URL
            target_dir: Target directory (creates temp dir if None)
            cleanup_after: Whether to clean up temp dir after analysis
            on_progress: Optional callback(message: str) for progress updates

        Returns:
            Path to cloned repository

        Raises:
            ValueError: If URL is invalid
            RuntimeError: If git clone fails after all retries
        """

        def _progress(msg):
            if on_progress:
                on_progress(msg)
            logger.info(msg)

        # Validate and parse URL
        owner, repo = GitURLParser.parse(url)

        # Determine target directory
        created_temp = False
        if target_dir is None:
            target_dir = Path(tempfile.mkdtemp(prefix=f"miie_{owner}_{repo}_"))
            created_temp = True
        else:
            target_dir = Path(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

        # Prepare git clone command — never embed token in URL
        # Use GIT_ASKPASS to supply credentials safely (avoids token-in-URL leak)
        clone_url = url
        git_askpass_env = None
        if self.auth_token:
            if url.startswith("https://"):
                clone_url = url.replace("https://", "https://git@")
            elif url.startswith("http://"):
                clone_url = url.replace("http://", "https://git@")
            # Create a temp script that returns the token for git credential prompts
            import os
            import stat

            askpass_script = Path(tempfile.mktemp(suffix=".cmd" if os.name == "nt" else ".sh"))
            if os.name == "nt":
                askpass_script.write_text(f"@echo {self.auth_token}\n", encoding="utf-8")
            else:
                askpass_script.write_text(f"#!/bin/sh\necho {self.auth_token}\n", encoding="utf-8")
                os.chmod(askpass_script, stat.S_IRUSR | stat.S_IXUSR)
            git_askpass_env = {"GIT_ASKPASS": str(askpass_script)}

        # Build git clone command
        cmd = ["git", "clone"]
        if self.shallow_depth is not None and self.shallow_depth > 0:
            cmd.extend(["--depth", str(self.shallow_depth)])
        cmd.extend([clone_url, str(target_dir)])

        _progress(f"Cloning {owner}/{repo} (depth={self.shallow_depth})...")

        # Execute git clone with retry and timeout
        last_error = None
        clone_env = None
        if git_askpass_env:
            import os

            clone_env = {**os.environ, **git_askpass_env}
        for attempt in range(MAX_RETRIES):
            try:
                _result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True,
                    timeout=GIT_TIMEOUT,
                    env=clone_env,
                )
                # Clone succeeded
                if attempt > 0:
                    logger.info("Clone succeeded on attempt %d/%d", attempt + 1, MAX_RETRIES)
                _progress(f"Clone complete: {target_dir}")
                break
            except subprocess.TimeoutExpired as e:
                last_error = e
                _progress(f"Clone timed out after {GIT_TIMEOUT}s (attempt {attempt+1}/{MAX_RETRIES})")
                # Clean up partial clone on timeout
                if target_dir.exists():
                    shutil.rmtree(target_dir, ignore_errors=True)
                if created_temp:
                    target_dir = Path(tempfile.mkdtemp(prefix=f"miie_{owner}_{repo}_"))
                    cmd[-1] = str(target_dir)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
            except subprocess.CalledProcessError as e:
                last_error = e
                error_msg = f"Failed to clone {url}\n"
                if e.stderr:
                    error_msg += f"Git error: {e.stderr}"
                _progress(f"Clone failed (attempt {attempt+1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
            except Exception as e:
                last_error = e
                _progress(f"Clone error (attempt {attempt+1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
        else:
            # All retries exhausted
            error_msg = f"Failed to clone {url} after {MAX_RETRIES} attempts"
            if last_error:
                error_msg += f": {last_error}"
            raise RuntimeError(error_msg)

        # Cleanup GIT_ASKPASS script
        if git_askpass_env and git_askpass_env.get("GIT_ASKPASS"):
            try:
                Path(git_askpass_env["GIT_ASKPASS"]).unlink(missing_ok=True)
            except Exception:
                pass

        # Setup cleanup if requested
        if cleanup_after:
            import atexit

            atexit.register(self._cleanup_temp_dir, target_dir)

        return target_dir

    def _cleanup_temp_dir(self, temp_dir: Path) -> None:
        """Clean up temporary directory."""
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                logger.info("Cleaned up temp dir: %s", temp_dir)
        except Exception as e:
            logger.warning("Failed to clean up temp dir %s: %s", temp_dir, e)
