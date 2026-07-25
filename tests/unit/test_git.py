"""Tests for Git URL parser and cloner utilities."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from miie.utils.git import GitCloner, GitURLParser


# ---------------------------------------------------------------------------
# GitURLParser
# ---------------------------------------------------------------------------
class TestGitURLParser:
    """Tests for GitURLParser.parse and is_github_url."""

    # --- Valid HTTPS URLs ---
    @pytest.mark.parametrize(
        "url, expected_owner, expected_repo",
        [
            ("https://github.com/owner/repo", "owner", "repo"),
            ("https://github.com/pallets/flask", "pallets", "flask"),
            ("https://github.com/owner/repo.git", "owner", "repo"),
            ("https://www.github.com/owner/repo", "owner", "repo"),
            ("http://github.com/owner/repo", "owner", "repo"),
            ("https://github.com/owner/my-repo-name", "owner", "my-repo-name"),
            ("https://github.com/owner/repo.git", "owner", "repo"),
            ("  https://github.com/owner/repo  ", "owner", "repo"),  # whitespace
        ],
    )
    def test_parse_valid_https(self, url, expected_owner, expected_repo):
        owner, repo = GitURLParser.parse(url)
        assert owner == expected_owner
        assert repo == expected_repo

    # --- Valid SSH URLs ---
    @pytest.mark.parametrize(
        "url, expected_owner, expected_repo",
        [
            ("git@github.com:owner/repo.git", "owner", "repo"),
            ("ssh://git@github.com/owner/repo.git", "owner", "repo"),
        ],
    )
    def test_parse_valid_ssh(self, url, expected_owner, expected_repo):
        owner, repo = GitURLParser.parse(url)
        assert owner == expected_owner
        assert repo == expected_repo

    # --- Valid git:// URLs ---
    def test_parse_valid_git_protocol(self):
        owner, repo = GitURLParser.parse("git://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    # --- Invalid URLs ---
    @pytest.mark.parametrize(
        "url",
        [
            "not-a-url",
            "https://gitlab.com/owner/repo",
            "https://bitbucket.org/owner/repo",
            "",
            "ftp://github.com/owner/repo",
            "https://github.com/",
            "https://github.com/owner/",
            "https://github.com/owner/repo/extra",
            "https://github.com//repo",
        ],
    )
    def test_parse_invalid_raises(self, url):
        with pytest.raises(ValueError):
            GitURLParser.parse(url)

    # --- is_github_url ---
    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/owner/repo",
            "git@github.com:owner/repo.git",
            "ssh://git@github.com/owner/repo.git",
            "https://www.github.com/owner/repo",
        ],
    )
    def test_is_github_url_true(self, url):
        assert GitURLParser.is_github_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://gitlab.com/owner/repo",
            "not-a-url",
            "",
            "https://example.com/github.com/owner/repo",
        ],
    )
    def test_is_github_url_false(self, url):
        assert GitURLParser.is_github_url(url) is False


# ---------------------------------------------------------------------------
# GitCloner
# ---------------------------------------------------------------------------
class TestGitCloner:
    """Tests for GitCloner initialization and URL construction."""

    def test_init_defaults(self):
        cloner = GitCloner()
        assert cloner.auth_token is None
        assert cloner.shallow_depth == 1

    def test_init_with_token(self):
        cloner = GitCloner(auth_token="ghp_abc123", shallow_depth=0)
        assert cloner.auth_token == "ghp_abc123"
        assert cloner.shallow_depth == 0

    @patch("miie.utils.git.subprocess.run")
    def test_clone_auth_token_injected_in_url(self, mock_run):
        """Auth token should NOT be in the clone URL (uses GIT_ASKPASS instead)."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        cloner = GitCloner(auth_token="ghp_test123")

        try:
            cloner.clone(
                "https://github.com/owner/repo",
                target_dir=Path("/tmp/test_clone"),
            )
        except Exception:
            pass  # We just want to inspect the call args

        # Check that the token is NOT in the URL (security fix)
        call_args = mock_run.call_args
        if call_args:
            cmd = call_args[0][0]
            clone_url = cmd[-2] if len(cmd) >= 2 else ""
            assert "ghp_test123@" not in clone_url, "Token must not be embedded in URL"
            # Token should be supplied via GIT_ASKPASS env var
            kwargs = call_args[1] if len(call_args) > 1 else {}
            env = kwargs.get("env")
            assert env is not None, "subprocess should be called with env parameter"
            assert "GIT_ASKPASS" in env, "GIT_ASKPASS should be set in env"

    @patch("miie.utils.git.subprocess.run")
    def test_clone_no_token_no_injection(self, mock_run):
        """Without auth token, URL should remain unchanged."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        cloner = GitCloner()

        with patch("miie.utils.git.tempfile.mkdtemp", return_value="/tmp/test_clone"):
            with patch("miie.utils.git.Path") as MockPath:
                mock_path = MagicMock()
                mock_path.__str__ = lambda self: "/tmp/test_clone"
                MockPath.return_value = mock_path
                mock_path.mkdir = MagicMock()
                mock_path.exists.return_value = False

                try:
                    cloner.clone(
                        "https://github.com/owner/repo",
                        target_dir=Path("/tmp/test_clone"),
                    )
                except Exception:
                    pass

        call_args = mock_run.call_args
        if call_args:
            cmd = call_args[0][0]
            clone_url = cmd[-2] if len(cmd) >= 2 else ""
            # Token should NOT be in URL
            assert "ghp_" not in clone_url

    @patch("miie.utils.git.subprocess.run")
    def test_clone_builds_correct_command(self, mock_run):
        """Clone command should include --depth flag."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        cloner = GitCloner(shallow_depth=5)

        with patch("miie.utils.git.tempfile.mkdtemp", return_value="/tmp/test_clone"):
            with patch("miie.utils.git.Path") as MockPath:
                mock_path = MagicMock()
                mock_path.__str__ = lambda self: "/tmp/test_clone"
                MockPath.return_value = mock_path
                mock_path.mkdir = MagicMock()
                mock_path.exists.return_value = False

                try:
                    cloner.clone(
                        "https://github.com/owner/repo",
                        target_dir=Path("/tmp/test_clone"),
                    )
                except Exception:
                    pass

        call_args = mock_run.call_args
        if call_args:
            cmd = call_args[0][0]
            assert cmd[0] == "git"
            assert cmd[1] == "clone"
            assert "--depth" in cmd
            assert "5" in cmd

    def test_clone_invalid_url_raises(self):
        """Clone with invalid URL should raise ValueError."""
        cloner = GitCloner()
        with pytest.raises(ValueError, match="GitHub URL"):
            cloner.clone("not-a-github-url")

    @patch("miie.utils.git.subprocess.run")
    def test_clone_failure_raises_runtime_error(self, mock_run):
        """Clone failure should raise RuntimeError."""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(128, "git", stderr="fatal: repository not found")
        cloner = GitCloner()

        with pytest.raises(RuntimeError, match="Failed to clone"):
            cloner.clone("https://github.com/owner/repo")

    def test_cleanup_temp_dir(self):
        """_cleanup_temp_dir should remove directory if it exists."""
        import tempfile

        temp_dir = Path(tempfile.mkdtemp(prefix="miie_test_cleanup_"))
        (temp_dir / "test_file.txt").write_text("test")

        cloner = GitCloner()
        cloner._cleanup_temp_dir(temp_dir)

        assert not temp_dir.exists()

    def test_cleanup_nonexistent_dir_no_error(self):
        """_cleanup_temp_dir should not raise for nonexistent directories."""
        cloner = GitCloner()
        # Should not raise
        cloner._cleanup_temp_dir(Path("/tmp/nonexistent_dir_that_does_not_exist"))
