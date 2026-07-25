"""Workspace Persistence.

Provides session persistence, bookmark management, and workspace history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .engine import WorkspaceEngine


class WorkspacePersistence:
    """Manages workspace persistence to disk."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        if base_dir is None:
            base_dir = Path.home() / ".miie" / "workspaces"
        self.base_dir = Path(base_dir)
        self._ensure_dir()

    def _sanitize_id(self, workspace_id: str) -> str:
        """Sanitize workspace_id to prevent path traversal.

        Strips traversal sequences and non-alphanumeric characters (except - and _).
        Uses iterative replacement to handle encoded sequences like '....//'.
        """
        import re

        safe = workspace_id
        # Iteratively strip all .. sequences (handles ....// → traversal attempt)
        while ".." in safe:
            safe = safe.replace("..", "_")
        safe = safe.replace("/", "_").replace("\\", "_")
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", safe)
        return safe

    def _ensure_dir(self) -> None:
        """Ensure base directory exists."""
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, workspace: WorkspaceEngine) -> str:
        """Save workspace state to disk.

        Args:
            workspace: Workspace engine to save

        Returns:
            Path to saved workspace file
        """
        workspace_id = workspace.state.workspace_id
        safe_id = self._sanitize_id(workspace_id)
        workspace_dir = self.base_dir / safe_id
        # Defense in depth: verify path stays within base_dir
        if not workspace_dir.resolve().is_relative_to(self.base_dir.resolve()):
            raise ValueError(f"Workspace ID resolves outside base directory: {workspace_id}")
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Save main state
        state_file = workspace_dir / "workspace.json"
        state_data = workspace.to_cache_data()
        state_file.write_text(json.dumps(state_data, indent=2, default=str))

        # Save bookmarks separately
        bookmarks_file = workspace_dir / "bookmarks.json"
        bookmarks_file.write_text(json.dumps(workspace.get_bookmarks(), indent=2, default=str))

        # Save export history
        exports_file = workspace_dir / "exports.json"
        exports_file.write_text(json.dumps(workspace.get_export_history(), indent=2, default=str))

        return str(workspace_dir)

    def load(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Load workspace state from disk.

        Args:
            workspace_id: ID of workspace to load

        Returns:
            Workspace cache data or None if not found
        """
        safe_id = self._sanitize_id(workspace_id)
        workspace_dir = self.base_dir / safe_id
        # Defense in depth: verify path stays within base_dir
        if not workspace_dir.resolve().is_relative_to(self.base_dir.resolve()):
            return None
        state_file = workspace_dir / "workspace.json"

        if not state_file.exists():
            return None

        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """List all saved workspaces.

        Returns:
            List of workspace summaries
        """
        workspaces = []
        if not self.base_dir.exists():
            return workspaces

        for workspace_dir in self.base_dir.iterdir():
            if not workspace_dir.is_dir():
                continue

            state_file = workspace_dir / "workspace.json"
            if not state_file.exists():
                continue

            try:
                data = json.loads(state_file.read_text())
                workspaces.append(
                    {
                        "workspace_id": data.get("workspace_id", workspace_dir.name),
                        "created_at": data.get("created_at", ""),
                        "repo_path": data.get("repo_path", ""),
                        "repo_id": data.get("repo_id", ""),
                        "total_commits": data.get("total_commits", 0),
                    }
                )
            except (json.JSONDecodeError, OSError):
                continue

        return sorted(workspaces, key=lambda x: x.get("created_at", ""), reverse=True)

    def delete(self, workspace_id: str) -> bool:
        """Delete a saved workspace.

        Args:
            workspace_id: ID of workspace to delete

        Returns:
            True if deleted successfully
        """
        import shutil

        safe_id = self._sanitize_id(workspace_id)
        workspace_dir = self.base_dir / safe_id
        # Verify resolved path is within base_dir (defense in depth)
        if not workspace_dir.resolve().is_relative_to(self.base_dir.resolve()):
            raise ValueError(f"Workspace ID resolves outside base directory: {workspace_id}")
        if workspace_dir.exists():
            try:
                shutil.rmtree(workspace_dir)
                return True
            except OSError:
                return False
        return False

    def get_bookmarks(self, workspace_id: str) -> List[Dict[str, Any]]:
        """Get bookmarks for a workspace."""
        safe_id = self._sanitize_id(workspace_id)
        workspace_dir = self.base_dir / safe_id
        # Defense in depth: verify path stays within base_dir
        if not workspace_dir.resolve().is_relative_to(self.base_dir.resolve()):
            return []
        bookmarks_file = workspace_dir / "bookmarks.json"

        if not bookmarks_file.exists():
            return []

        try:
            return json.loads(bookmarks_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def save_bookmarks(self, workspace_id: str, bookmarks: List[Dict[str, Any]]) -> bool:
        """Save bookmarks for a workspace."""
        safe_id = self._sanitize_id(workspace_id)
        workspace_dir = self.base_dir / safe_id
        bookmarks_file = workspace_dir / "bookmarks.json"

        try:
            bookmarks_file.write_text(json.dumps(bookmarks, indent=2, default=str))
            return True
        except OSError:
            return False

    def get_export_history(self, workspace_id: str) -> List[Dict[str, Any]]:
        """Get export history for a workspace."""
        safe_id = self._sanitize_id(workspace_id)
        workspace_dir = self.base_dir / safe_id
        exports_file = workspace_dir / "exports.json"

        if not exports_file.exists():
            return []

        try:
            return json.loads(exports_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def save_export_history(self, workspace_id: str, exports: List[Dict[str, Any]]) -> bool:
        """Save export history for a workspace."""
        safe_id = self._sanitize_id(workspace_id)
        workspace_dir = self.base_dir / safe_id
        exports_file = workspace_dir / "exports.json"

        try:
            exports_file.write_text(json.dumps(exports, indent=2, default=str))
            return True
        except OSError:
            return False
