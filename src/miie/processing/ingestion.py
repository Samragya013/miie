import datetime
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Union

from miie.contracts.errors import IngestionError
from miie.contracts.interfaces import IIngestionEngine
from miie.schemas.models import RepositoryContext
from miie.utils.git import GIT_TIMEOUT, GitCloner, GitURLParser
from miie.utils.workspace import detect_workspace

logger = logging.getLogger(__name__)

# Safe environment for git subprocess calls — disables system gitconfig
# and prevents git hooks from executing during analysis
_GIT_SAFE_ENV = {
    **os.environ,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_EDITOR": ":",
    "GIT_SEQUENCE_EDITOR": ":",
    "GIT_MERGE_AUTOEDIT": "no",
}


def validate_repository(repo_path: Union[str, Path]) -> None:
    """
    Validate that the given path is a valid Git repository.

    Args:
        repo_path: Path to the repository as a string or Path object.
                  Can also be a GitHub URL.

    Raises:
        IngestionError: If the path does not exist, is not a directory,
                        does not contain a .git subdirectory, or if a
                        traversal attempt is detected.
    """
    # Convert to string for URL detection
    path_str = str(repo_path)

    # Check if it's a GitHub URL
    if GitURLParser.is_github_url(path_str):
        # For URLs, we'll validate by attempting to clone
        # We can't validate without cloning, so we'll let the clone operation handle validation
        return

    # For local paths, perform traditional validation
    # Convert to Path if string
    if isinstance(repo_path, str):
        repo_path = Path(repo_path)
    elif not isinstance(repo_path, Path):
        raise IngestionError("repo_path must be a string or Path object")

    # Perform safe path resolution to prevent traversal attacks
    try:
        resolved_path = repo_path.resolve()
    except Exception as e:
        raise IngestionError(f"Failed to resolve path: {e}")

    # Check if path exists
    if not resolved_path.exists():
        raise IngestionError(f"Repository path does not exist: {resolved_path}")

    # Check if path is a directory
    if not resolved_path.is_dir():
        raise IngestionError(f"Repository path is not a directory: {resolved_path}")

    # Check if .git subdirectory exists
    git_dir = resolved_path / ".git"
    if not git_dir.exists():
        raise IngestionError(f"Repository path does not contain a .git directory: {resolved_path}")

    # If all checks pass, return nothing (implicitly None)


def cache_path_for_repository(repo_id: str) -> Path:
    """
    Calculate the cache path for a given repository ID.

    Args:
        repo_id: A string identifier for the repository.

    Returns:
        A Path object representing the normalized cache path for the repository.

    Raises:
        ValueError: If the resulting path would escape the cache root.
    """
    cache_root = Path.home() / ".miie" / "cache"
    repo_cache_path = cache_root / "repos" / repo_id
    normalized_path = repo_cache_path.resolve()
    resolved_cache_root = cache_root.resolve()
    try:
        normalized_path.relative_to(resolved_cache_root)
    except ValueError:
        raise ValueError(f"Attempted to escape cache root: {normalized_path} is not under {resolved_cache_root}")
    return normalized_path


class RepositoryIngestionEngine(IIngestionEngine):
    def __init__(self, auth_token: Optional[str] = None):
        """Initialize ingestion engine.

        Args:
            auth_token: GitHub personal access token for private repos.
        """
        self.auth_token = auth_token

    def ingest(
        self,
        repo_path: str,
        cache_dir: Optional[Path] = None,
        keep_cache: bool = False,
        shallow_depth: Optional[int] = None,
        on_progress=None,
    ) -> RepositoryContext:
        """
        Ingest repository metadata and return a RepositoryContext object.

        Args:
            repo_path: Path to the repository as a string. Can be a local path
                      or a GitHub URL (e.g., https://github.com/owner/repo).
            cache_dir: Optional directory for caching (not used in this implementation).
            keep_cache: Whether to keep cache (not used).
            shallow_depth: Optional depth for shallow clone (not used).
            on_progress: Optional callback(message: str) for progress updates.

        Returns:
            RepositoryContext: Populated with repository metadata.

        Raises:
            IngestionError: If any step fails.
        """
        # Handle GitHub URLs
        if GitURLParser.is_github_url(repo_path):
            # Clone the repository
            cloned_path = self._clone_from_url(repo_path, shallow_depth, on_progress=on_progress)
            # Extract metadata from cloned repo
            repo_id = self._get_repo_id(cloned_path)
            _repository_name = self._get_repository_name(cloned_path)
            total_commits = self._get_commit_count(cloned_path)
            first_commit_date = self._get_first_commit_date(cloned_path)
            last_commit_date = self._get_last_commit_date(cloned_path)
            contributor_count = self._get_contributor_count(cloned_path)
            is_shallow = self._is_shallow_clone(cloned_path)
            is_fork = self._is_fork_repository(cloned_path)
            language_distribution = self._get_language_distribution(cloned_path)
            is_remote = True
            remote_url = repo_path
            path_obj = cloned_path
        else:
            # Validate the repository
            validate_repository(repo_path)
            path_obj = Path(repo_path) if isinstance(repo_path, str) else repo_path

        # Extract metadata
        repo_id = self._get_repo_id(path_obj)
        _repository_name = self._get_repository_name(path_obj)
        total_commits = self._get_commit_count(path_obj)
        first_commit_date = self._get_first_commit_date(path_obj)
        last_commit_date = self._get_last_commit_date(path_obj)
        contributor_count = self._get_contributor_count(path_obj)
        is_shallow = self._is_shallow_clone(path_obj)
        is_fork = self._is_fork_repository(path_obj)
        language_distribution = self._get_language_distribution(path_obj)
        is_remote = False
        remote_url = None

        # Empty repo guard
        if total_commits == 0:
            raise IngestionError(
                f"Repository has 0 commits: {path_obj}. "
                "MIIE requires at least one commit to extract metrics."
            )

        # Workspace detection (monorepo, pnpm, yarn, etc.)
        workspace_info = detect_workspace(path_obj)
        if workspace_info:
            logger.info(
                "Detected workspace: %s (%d packages)",
                workspace_info.tool,
                len(workspace_info.packages),
            )

        # Construct and return RepositoryContext
        try:
            ctx = RepositoryContext(
                repo_id=repo_id,
                local_path=path_obj.resolve(),
                is_remote=is_remote,
                remote_url=remote_url,
                total_commits=total_commits,
                first_commit_date=first_commit_date,
                last_commit_date=last_commit_date,
                contributor_count=contributor_count,
                is_shallow=is_shallow,
                is_fork=is_fork,
                language_distribution=language_distribution,
            )
            # Attach workspace info as extra attribute (not in frozen dataclass)
            if workspace_info:
                ctx._workspace_info = workspace_info  # type: ignore[attr-defined]
            return ctx
        except ValueError as e:
            raise IngestionError(f"Invalid repository context: {e}")

    def _clone_from_url(self, url: str, shallow_depth: Optional[int] = None, on_progress=None) -> Path:
        """
        Clone a GitHub repository from a URL.

        Args:
            url: GitHub repository URL.
            shallow_depth: Optional depth for shallow clone.
            on_progress: Optional callback(message: str) for progress updates.

        Returns:
            Path to cloned repository.

        Raises:
            IngestionError: If git clone fails.
        """
        # Create a temporary directory for cloning
        import tempfile

        temp_dir = Path(tempfile.mkdtemp(prefix="miie_clone_"))

        # Clone the repository
        try:
            cloner = GitCloner(auth_token=self.auth_token, shallow_depth=shallow_depth)
            cloned_path = cloner.clone(url, temp_dir, cleanup_after=True, on_progress=on_progress)
            return cloned_path
        except Exception as e:
            # Clean up temp dir if it exists
            if temp_dir.exists():
                import shutil

                shutil.rmtree(temp_dir)
            raise IngestionError(f"Failed to clone repository from {url}: {e}")

    def validate(self, context: RepositoryContext) -> bool:
        """
        Validate the repository context by checking if the local path is a valid Git repository.

        Args:
            context: Repository context containing the local path to validate.

        Returns:
            True if the repository is valid, False otherwise.
        """
        try:
            validate_repository(context.local_path)
            return True
        except IngestionError:
            return False

    # Helper methods
    @staticmethod
    def _get_repo_id(repo_path: Path) -> str:
        """
        Generate a unique repository ID based on the absolute path.

        Args:
            repo_path: Path to the repository.

        Returns:
            A string ID (using SHA256 hash of the absolute path).
        """
        import hashlib

        absolute_path = str(repo_path.resolve())
        return hashlib.sha256(absolute_path.encode()).hexdigest()

    @staticmethod
    def _get_repository_name(repo_path: Path) -> str:
        """
        Get the repository name (last part of the path).

        Args:
            repo_path: Path to the repository.

        Returns:
            The repository name.
        """
        return repo_path.name

    @staticmethod
    def _get_commit_count(repo_path: Path) -> int:
        """
        Get the total number of commits in the repository.

        Args:
            repo_path: Path to the repository.

        Returns:
            The number of commits.

        Raises:
            IngestionError: If the git command fails.
        """
        try:
            # Run git rev-list --count HEAD
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                timeout=GIT_TIMEOUT,
                env=_GIT_SAFE_ENV,
            )
            count_str = result.stdout.strip()
            return int(count_str)
        except subprocess.CalledProcessError as e:
            raise IngestionError(f"Failed to get commit count: {e.stderr.strip()}")
        except ValueError as e:
            raise IngestionError(f"Failed to parse commit count: {e}")

    @staticmethod
    def _get_first_commit_date(repo_path: Path) -> Optional[datetime.datetime]:
        """
        Get the date of the first commit.

        Args:
            repo_path: Path to the repository.

        Returns:
            datetime object of the first commit, or None if not available.
        """
        try:
            # Get the timestamp of the first commit (oldest)
            result = subprocess.run(
                ["git", "log", "--reverse", "--format=%at", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                timeout=GIT_TIMEOUT,
                env=_GIT_SAFE_ENV,
            )
            timestamp_str = result.stdout.strip().split("\n")[0] if result.stdout.strip() else None
            if timestamp_str is None:
                return None
            timestamp = int(timestamp_str)
            return datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
        except (subprocess.CalledProcessError, ValueError, IndexError):
            # If we fail, we return None (optional field)
            return None

    @staticmethod
    def _get_last_commit_date(repo_path: Path) -> Optional[datetime.datetime]:
        """
        Get the date of the most recent commit.

        Args:
            repo_path: Path to the repository.

        Returns:
            datetime object of the last commit, or None if not available.
        """
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%at"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                timeout=GIT_TIMEOUT,
                env=_GIT_SAFE_ENV,
            )
            timestamp_str = result.stdout.strip()
            if not timestamp_str:
                return None
            timestamp = int(timestamp_str)
            return datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
        except (subprocess.CalledProcessError, ValueError):
            return None

    @staticmethod
    def _get_contributor_count(repo_path: Path) -> int:
        """
        Get the number of unique contributors.

        Args:
            repo_path: Path to the repository.

        Returns:
            The number of contributors.

        Raises:
            IngestionError: If the git command fails.
        """
        try:
            # Use git shortlog to get commit counts per contributor, then count lines
            result = subprocess.run(
                ["git", "shortlog", "-sn", "--all"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                timeout=GIT_TIMEOUT,
                env=_GIT_SAFE_ENV,
            )
            # Each line is a contributor, empty output means 0
            lines = [line for line in result.stdout.strip().split("\n") if line]
            return len(lines)
        except subprocess.CalledProcessError as e:
            raise IngestionError(f"Failed to get contributor count: {e.stderr.strip()}")

    @staticmethod
    def _is_shallow_clone(repo_path: Path) -> bool:
        """
        Check if the repository is a shallow clone.

        Args:
            repo_path: Path to the repository.

        Returns:
            True if shallow clone, False otherwise.
        """
        git_dir = repo_path / ".git"
        shallow_file = git_dir / "shallow"
        return shallow_file.exists()

    @staticmethod
    def _is_fork_repository(repo_path: Path) -> bool:
        """
        Check if the repository is a fork.
        Without remote information, we cannot reliably detect forks.
        Return False as placeholder.

        Args:
            repo_path: Path to the repository.

        Returns:
            False (cannot detect locally).
        """
        # We cannot determine if it's a fork without remote URLs.
        # We could try to get remote URLs, but even then,fork detection is not reliable.
        # For now, return False.
        return False

    @staticmethod
    def _get_language_distribution(repo_path: Path) -> Optional[dict]:
        """
        Get the language distribution in the repository.
        Not implemented; returns None as per requirements.

        Args:
            repo_path: Path to the repository.

        Returns:
            None.
        """
        return None
