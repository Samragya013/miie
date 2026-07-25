"""
Workspace and monorepo detection for MIIE.

Detects monorepo workspace configurations (pnpm, lerna, nx, turbo, yarn,
Cargo workspaces, Go workspaces) and provides file-path filtering for
package-scoped analysis.

Scalability: allows analyzing individual packages within large monorepos
without processing the entire repository's commit history.

Reference: MIIE Scalability Phase 6c
"""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Workspace tool detection patterns
# ---------------------------------------------------------------------------

_WORKSPACE_MARKERS: Dict[str, str] = {
    "pnpm": "pnpm-workspace.yaml",
    "yarn": "package.json",  # check for "workspaces" key
    "lerna": "lerna.json",
    "nx": "nx.json",
    "turbo": "turbo.json",
    "cargo": "Cargo.toml",  # check for [workspace] section
    "go": "go.work",
}

# Files that indicate a sub-package within a monorepo
_PACKAGE_MARKERS = {
    "package.json",
    "Cargo.toml",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
}


class WorkspaceInfo:
    """Detected workspace/monorepo configuration."""

    def __init__(
        self,
        tool: str,
        root: Path,
        packages: Optional[List[str]] = None,
        package_paths: Optional[List[Path]] = None,
    ):
        self.tool = tool
        self.root = root
        self.packages = packages or []
        self.package_paths = package_paths or []

    @property
    def is_monorepo(self) -> bool:
        return bool(self.packages)

    def get_package_prefixes(self) -> Set[str]:
        """Return file-path prefixes that belong to workspace packages.

        Handles complex glob patterns like ``packages/*/src`` by expanding
        them against the actual filesystem, with a fallback to simple
        prefix stripping for patterns that cannot be expanded.
        """
        prefixes: Set[str] = set()
        for pkg in self.packages:
            # Expand globs against the real workspace root
            expanded = _expand_glob_prefixes(pkg, self.root)
            if expanded:
                prefixes.update(expanded)
            else:
                # Fallback: simple suffix stripping
                if pkg.endswith("/*"):
                    prefixes.add(pkg[:-2] + "/")
                elif pkg.endswith("/**"):
                    prefixes.add(pkg[:-3] + "/")
                else:
                    prefixes.add(pkg + "/")
        return prefixes

    def __repr__(self) -> str:
        return f"WorkspaceInfo(tool={self.tool!r}, packages={len(self.packages)}, " f"is_monorepo={self.is_monorepo})"


def detect_workspace(repo_path: Path) -> Optional[WorkspaceInfo]:
    """Detect monorepo/workspace configuration in a repository.

    Performs a bounded recursive walk (max depth 3) to handle nested
    workspaces (e.g., monorepo inside a submodule).  Symlinks are
    followed only if they resolve within the repo root to prevent
    infinite loops.

    Args:
        repo_path: Path to the repository root.

    Returns:
        WorkspaceInfo if a workspace is detected, None otherwise.
    """
    if not repo_path.is_dir():
        return None

    resolved_root = repo_path.resolve()
    result = _detect_workspace_recursive(resolved_root, resolved_root, depth=0, max_depth=3)
    return result


def _detect_workspace_recursive(
    current_dir: Path,
    repo_root: Path,
    depth: int,
    max_depth: int,
) -> Optional[WorkspaceInfo]:
    """Recursive workspace detection with symlink cycle prevention.

    Args:
        current_dir: Directory being inspected.
        repo_root: Original repository root (for path calculations).
        depth: Current recursion depth.
        max_depth: Maximum allowed depth (prevents runaway walks).
    """
    if depth > max_depth:
        return None

    # --- Priority-ordered config checks (same as before) ---
    result = _try_workspace_configs(current_dir, repo_root)
    if result is not None:
        return result

    # --- Recurse into subdirectories ---
    try:
        for entry in os.scandir(current_dir):
            if not entry.is_dir(follow_symlinks=False):
                continue

            child = Path(entry.path)

            # Issue 6: Follow symlinks only if resolved target is inside repo
            try:
                resolved_child = child.resolve()
                if not str(resolved_child).startswith(str(repo_root)):
                    continue
            except (OSError, ValueError):
                continue

            # Skip VCS directories
            if child.name in {".git", ".svn", ".hg"}:
                continue

            nested = _detect_workspace_recursive(child, repo_root, depth + 1, max_depth)
            if nested is not None:
                return nested
    except PermissionError:
        pass

    return None


def _try_workspace_configs(directory: Path, repo_root: Path) -> Optional[WorkspaceInfo]:
    """Check a single directory for workspace config files.

    Returns WorkspaceInfo if found, None otherwise.
    """
    # pnpm
    pnpm_file = directory / "pnpm-workspace.yaml"
    if pnpm_file.exists():
        packages = _parse_pnpm_workspace(pnpm_file)
        if packages:
            return WorkspaceInfo(tool="pnpm", root=repo_root, packages=packages)

    # lerna
    lerna_file = directory / "lerna.json"
    if lerna_file.exists():
        packages = _parse_lerna_json(lerna_file)
        if packages:
            return WorkspaceInfo(tool="lerna", root=repo_root, packages=packages)

    # nx
    nx_file = directory / "nx.json"
    if nx_file.exists():
        packages = _parse_nx_workspace(directory)
        if packages:
            return WorkspaceInfo(tool="nx", root=repo_root, packages=packages)

    # turbo
    turbo_file = directory / "turbo.json"
    if turbo_file.exists():
        packages = _parse_turbo_workspace(directory)
        if packages:
            return WorkspaceInfo(tool="turbo", root=repo_root, packages=packages)

    # yarn workspaces
    pkg_json = directory / "package.json"
    if pkg_json.exists():
        packages = _parse_yarn_workspaces(pkg_json)
        if packages:
            return WorkspaceInfo(tool="yarn", root=repo_root, packages=packages)

    # Cargo workspaces
    cargo_toml = directory / "Cargo.toml"
    if cargo_toml.exists():
        packages = _parse_cargo_workspace(cargo_toml)
        if packages:
            return WorkspaceInfo(tool="cargo", root=repo_root, packages=packages)

    # Go workspaces
    go_work = directory / "go.work"
    if go_work.exists():
        packages = _parse_go_workspace(go_work)
        if packages:
            return WorkspaceInfo(tool="go", root=repo_root, packages=packages)

    return None


def detect_package_path(repo_path: Path, sub_path: str) -> Optional[Path]:
    """Detect if a sub-path is a package within a monorepo.

    Args:
        repo_path: Repository root.
        sub_path: Relative path within the repo (e.g., "packages/core").

    Returns:
        Resolved path if valid, None otherwise.
    """
    candidate = (repo_path / sub_path).resolve()
    if not candidate.is_dir():
        return None

    # Check if the sub-path contains a package marker
    for marker in _PACKAGE_MARKERS:
        if (candidate / marker).exists():
            return candidate

    return None


def filter_commits_by_path(
    commits: List[Dict],
    prefixes: Set[str],
) -> List[Dict]:
    """Filter commits to only those touching files with matching path prefixes.

    Args:
        commits: List of commit dicts with 'files' key (list of file paths).
        prefixes: File-path prefixes to include (e.g., {"packages/core/"}).

    Returns:
        Filtered list of commits.
    """
    if not prefixes:
        return commits

    filtered = []
    for commit in commits:
        files = commit.get("files", [])
        if any(any(path.startswith(prefix) for prefix in prefixes) for path in files):
            filtered.append(commit)
    return filtered


# ---------------------------------------------------------------------------
# Glob prefix expansion
# ---------------------------------------------------------------------------


def _expand_glob_prefixes(pattern: str, root: Path) -> Set[str]:
    """Expand a workspace glob pattern into concrete directory prefixes.

    For patterns containing ``*`` (single-level wildcards), this expands
    them against the real filesystem rooted at ``root`` and returns the
    matching directories as trailing-slash prefixes.

    For patterns with ``**`` (recursive wildcards), falls back to simple
    prefix stripping since full recursive expansion is expensive.

    Returns an empty set when expansion is not possible (e.g., pattern
    contains characters that cannot be resolved on the filesystem).
    """
    if "*" not in pattern:
        return set()

    # patterns with ** — too expensive to expand recursively
    if "**" in pattern:
        return set()

    # patterns with * — expand against the filesystem
    if "*" in pattern:
        prefixes: Set[str] = set()
        try:
            for match in root.glob(pattern):
                if match.is_dir():
                    # Return the path relative to root with trailing slash
                    rel = match.relative_to(root)
                    prefixes.add(str(rel).replace("\\", "/") + "/")
        except (OSError, ValueError):
            return set()
        return prefixes

    return set()


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------


def _parse_pnpm_workspace(path: Path) -> List[str]:
    """Parse pnpm-workspace.yaml for package globs."""
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and "packages" in data:
            pkgs = data["packages"]
            if isinstance(pkgs, list):
                return [str(p) for p in pkgs if isinstance(p, str)]
    except Exception as e:
        logger.debug("Failed to parse pnpm-workspace.yaml: %s", e)
    return []


def _parse_lerna_json(path: Path) -> List[str]:
    """Parse lerna.json for package globs."""
    try:
        import json

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        packages = data.get("packages") or data.get("workspaces", [])
        if isinstance(packages, list):
            return [str(p) for p in packages if isinstance(p, str)]
    except Exception as e:
        logger.debug("Failed to parse lerna.json: %s", e)
    return []


def _parse_yarn_workspaces(path: Path) -> List[str]:
    """Parse package.json for yarn workspaces."""
    try:
        import json

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        workspaces = data.get("workspaces", [])
        if isinstance(workspaces, list):
            return [str(w) for w in workspaces if isinstance(w, str)]
        if isinstance(workspaces, dict) and "packages" in workspaces:
            return [str(w) for w in workspaces["packages"] if isinstance(w, str)]
    except Exception as e:
        logger.debug("Failed to parse package.json workspaces: %s", e)
    return []


def _parse_nx_workspace(repo_path: Path) -> List[str]:
    """Detect nx workspace packages by scanning projects.json or workspace layout."""
    try:
        import json

        projects_json = repo_path / "project.json"
        if projects_json.exists():
            with open(projects_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "projects" in data:
                return list(data["projects"].keys())

        # Fallback: scan for nx.json + workspace pattern
        nx_json = repo_path / "nx.json"
        if nx_json.exists():
            with open(nx_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            # nx.json doesn't always have package paths directly
            # Look for workspaceLayout or defaultProject
            return []
    except Exception as e:
        logger.debug("Failed to detect nx workspace: %s", e)
    return []


def _parse_turbo_workspace(repo_path: Path) -> List[str]:
    """Detect turbo workspace packages from turbo.json and package.json."""
    try:
        import json

        pkg_json = repo_path / "package.json"
        if pkg_json.exists():
            with open(pkg_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            workspaces = data.get("workspaces", [])
            if isinstance(workspaces, list):
                return [str(w) for w in workspaces if isinstance(w, str)]
            if isinstance(workspaces, dict) and "packages" in workspaces:
                return [str(w) for w in workspaces["packages"] if isinstance(w, str)]
    except Exception as e:
        logger.debug("Failed to detect turbo workspace: %s", e)
    return []


def _parse_cargo_workspace(path: Path) -> List[str]:
    """Parse Cargo.toml for workspace members."""
    try:
        content = path.read_text(encoding="utf-8")
        in_workspace = False
        members: List[str] = []

        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "[workspace]":
                in_workspace = True
                continue
            if stripped.startswith("[") and in_workspace:
                break
            if in_workspace and stripped.startswith("members"):
                # Parse: members = ["path1", "path2"]
                # or: members = ["path1",\n  "path2"]
                bracket_start = stripped.find("[")
                if bracket_start >= 0:
                    bracket_content = stripped[bracket_start + 1 :]
                    if "]" in bracket_content:
                        bracket_content = bracket_content[: bracket_content.rfind("]")]
                    for item in bracket_content.split(","):
                        item = item.strip().strip('"').strip("'")
                        if item:
                            members.append(item)

        return members
    except Exception as e:
        logger.debug("Failed to parse Cargo.toml workspace: %s", e)
    return []


def _parse_go_workspace(path: Path) -> List[str]:
    """Parse go.work for workspace module paths."""
    try:
        content = path.read_text(encoding="utf-8")
        in_use = False
        modules: List[str] = []

        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "use (" or stripped.startswith("use "):
                if "(" in stripped:
                    in_use = True
                    continue
                else:
                    # Single-line: use ./path
                    parts = stripped.split()
                    if len(parts) >= 2:
                        modules.append(parts[1])
                    continue
            if in_use and stripped == ")":
                in_use = False
                continue
            if in_use and stripped.startswith("./"):
                modules.append(stripped)

        return modules
    except Exception as e:
        logger.debug("Failed to parse go.work: %s", e)
    return []
