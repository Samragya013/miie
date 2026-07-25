"""
CommitExtractor — extract observations from git commit history.

Traverses git log, extracts per-commit data (author, date, insertions,
deletions, message), and produces Observation objects grouped into
ObservationWindows inside an ObservationCollection.

Implements IMS Phase 3: CommitExtractor.

Reference: IMS-v1.0 Phase 3, ODSS-v1.0 §9, §7
"""

from __future__ import annotations

import datetime
import hashlib
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from miie.contracts.errors import ExtractionError
from miie.processing.observation.models import (
    ODSS_SCHEMA_VERSION,
    Observation,
    ObservationCollection,
    ObservationProvenance,
    ObservationRelationship,
    ObservationWindow,
    RelationshipType,
    generate_observation_id,
)

# Metric unit mapping (ODSS §9.2.6)
_METRIC_UNITS: Dict[str, str] = {
    "M-01": "ratio",
    "M-02": "count",
    "M-03": "ratio",
    "M-04": "ratio",
    "M-05": "hours",
    "M-06": "count",
    "M-07": "ratio",
}

# Metrics extractable from git commit data alone
_GIT_METRICS: frozenset[str] = frozenset({"M-02", "M-06"})

# Bot email patterns for exclusion
_BOT_PATTERNS: Tuple[str, ...] = (
    "dependabot",
    "renovate",
    "github-actions",
    "bot",
    "noreply",
    "ci-bot",
    "deploy-bot",
)

# Safe environment for git subprocess calls — disables hooks and prompts
_GIT_SAFE_ENV = {
    **os.environ,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_EDITOR": ":",
}

# Regex for parsing shortstat line
_INSERTIONS_RE = re.compile(r"(\d+)\s+insertion")
_DELETIONS_RE = re.compile(r"(\d+)\s+deletion")


def _parse_author_date(date_str: str) -> Optional[datetime.datetime]:
    """Parse an ISO 8601 author date string.

    Tries datetime.fromisoformat() first (works on 3.11+ with tz offsets).
    Falls back to manual parsing for Python 3.10 which does not support
    timezone offsets in fromisoformat().
    """
    try:
        return datetime.datetime.fromisoformat(date_str)
    except (ValueError, AttributeError):
        pass

    # Python 3.10 fallback: strip the tz offset and apply UTC.
    # Handles formats: ...+00:00, ...-05:00, ...+0530, ...Z
    tz_aware = date_str.endswith("Z")
    if tz_aware:
        naive_str = date_str[:-1]
    else:
        # Find last '+' or '-' that is followed by digits (tz offset)
        for i in range(len(date_str) - 1, 0, -1):
            if date_str[i] in ("+", "-") and date_str[i + 1 : i + 2].isdigit():
                naive_str = date_str[:i]
                break
        else:
            naive_str = date_str

    # Strip fractional seconds if present (strptime %f handles up to 6 digits)
    try:
        naive_dt = datetime.datetime.strptime(naive_str, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        try:
            naive_dt = datetime.datetime.strptime(naive_str, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None

    return naive_dt.replace(tzinfo=datetime.timezone.utc)


class CommitExtractor:
    """Extract observations from git commit history.

    Produces Observation objects for metrics derivable from git commits:
      - M-02 (Commit Frequency): value=1.0 per commit (count at window level)
      - M-06 (Code Churn): value=insertions+deletions per commit

    Other metrics (M-01, M-03–M-05, M-07) require external data sources
    and are not produced by CommitExtractor.

    The extractor is stateless — all state lives in the returned
    ObservationCollection.
    """

    EXTRACTOR_ID = "commit_extractor.v1"

    def extract_commits(
        self,
        context: Any,
        since: Optional[datetime.datetime] = None,
        until: Optional[datetime.datetime] = None,
        exclude_bots: bool = False,
        seed: Optional[int] = None,
    ) -> ObservationCollection:
        """Extract observations from git commit history.

        Args:
            context: RepositoryContext from ingestion.
            since: Inclusive start date filter.
            until: Inclusive end date filter.
            exclude_bots: Whether to exclude bot-authored commits.
            seed: Optional seed for deterministic provenance.

        Returns:
            ObservationCollection with one window containing all commit
            observations.

        Raises:
            ExtractionError: If git operations fail or context is invalid.
        """
        # --- Validate context ---
        repo_path = getattr(context, "local_path", None)
        repo_id = getattr(context, "repo_id", None)
        if repo_path is None or repo_id is None:
            raise ExtractionError("CommitExtractor requires a valid RepositoryContext")

        # --- Build and execute git log command ---
        commits = self._parse_git_log(repo_path, since, until, exclude_bots)

        if not commits:
            return self._empty_collection(repo_id, seed)

        # --- Determine analysis ID deterministically ---
        first_sha = commits[0]["sha"]
        last_sha = commits[-1]["sha"]
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        analysis_payload = f"{repo_id}:{first_sha}:{last_sha}:{now_iso}"
        analysis_id = hashlib.sha256(analysis_payload.encode()).hexdigest()[:16]

        # --- Build observations ---
        observations: List[Observation] = []
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        provenance = ObservationProvenance(
            extractor_id=self.EXTRACTOR_ID,
            extraction_timestamp=timestamp,
            seed=seed,
        )

        for commit in commits:
            sha = commit["sha"]
            author_date: datetime.datetime = commit["author_date"]
            insertions: int = commit["insertions"]
            deletions: int = commit["deletions"]
            churn_value = float(insertions + deletions)
            commit_ts = author_date.isoformat()

            commit_meta = {
                "author_name": commit["author_name"],
                "author_email": commit["author_email"],
                "message": commit["message"],
                "insertions": str(insertions),
                "deletions": str(deletions),
            }

            commit_observations: List[Observation] = []

            # --- M-02: Commit Frequency (one observation per commit) ---
            obs_m02 = Observation(
                observation_id=generate_observation_id("commit", sha, "M-02"),
                source_type="commit",
                source_id=sha,
                metric_id="M-02",
                value=1.0,
                unit="count",
                timestamp=commit_ts,
                quality="complete",
                provenance=provenance,
                metadata=commit_meta,
            )
            commit_observations.append(obs_m02)

            # --- M-06: Code Churn (one observation per commit) ---
            obs_m06 = Observation(
                observation_id=generate_observation_id("commit", sha, "M-06"),
                source_type="commit",
                source_id=sha,
                metric_id="M-06",
                value=churn_value,
                unit="count",
                timestamp=commit_ts,
                quality="complete",
                provenance=provenance,
                metadata=commit_meta,
                relationships=[
                    ObservationRelationship(
                        relationship_type=RelationshipType.DERIVED_FROM,
                        target_observation_id=generate_observation_id("commit", sha, "M-02"),
                    )
                ],
            )
            commit_observations.append(obs_m06)

            observations.extend(commit_observations)

        # --- Group into single window ---
        window = self._build_window(observations, commits)

        # --- Build collection ---
        return ObservationCollection(
            collection_id=generate_observation_id("commit", first_sha, "M-02"),
            repository_id=repo_id,
            analysis_id=analysis_id,
            windows=[window],
            total_observations=len(observations),
            total_metrics=len({obs.metric_id for obs in observations}),
            extraction_timestamp=timestamp,
            schema_version=ODSS_SCHEMA_VERSION,
        )

    # ------------------------------------------------------------------
    # Git log parsing
    # ------------------------------------------------------------------

    def _parse_git_log(
        self,
        repo_path: Any,
        since: Optional[datetime.datetime],
        until: Optional[datetime.datetime],
        exclude_bots: bool,
    ) -> List[Dict[str, Any]]:
        """Parse git log into structured commit dicts.

        Each dict contains:
            sha, author_name, author_email, author_date,
            message, insertions, deletions
        """
        format_str = "%H%n%an%n%ae%n%aI%n%s"

        cmd = [
            "git",
            "log",
            f"--format={format_str}",
            "--shortstat",
            "--no-merges",
        ]

        if since is not None:
            cmd.extend(["--since", since.strftime("%Y-%m-%d")])
        if until is not None:
            cmd.extend(["--until", until.strftime("%Y-%m-%d")])
        if exclude_bots:
            for pattern in _BOT_PATTERNS:
                cmd.extend(["--author", f"!{pattern}"])

        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                timeout=120,
                env=_GIT_SAFE_ENV,
            )
        except FileNotFoundError:
            raise ExtractionError("git executable not found")
        except subprocess.CalledProcessError as exc:
            # Empty repo (no commits) → return empty list, not error
            stderr = exc.stderr.strip() if exc.stderr else ""
            if "does not have any commits" in stderr or "fatal: bad default revision" in stderr:
                return []
            raise ExtractionError(f"git log failed: {stderr}")

        return self._parse_log_output(result.stdout)

    def _parse_log_output(self, raw_output: str) -> List[Dict[str, Any]]:
        """Parse raw git log --format output into commit dicts.

        Format per commit (5 header lines + optional shortstat):
            SHA
            Author Name
            Author Email
            Author Date (ISO)
            Subject
            [blank line or shortstat line]
        """
        lines = raw_output.split("\n")
        commits: List[Dict[str, Any]] = []

        idx = 0
        n = len(lines)

        while idx < n:
            sha = lines[idx].strip()
            idx += 1

            # Skip empty lines between commits
            if not sha:
                continue

            # Must have at least 4 more lines for author_name, email, date, subject
            if idx + 3 >= n:
                break

            author_name = lines[idx].strip()
            idx += 1
            author_email = lines[idx].strip()
            idx += 1
            date_str = lines[idx].strip()
            idx += 1
            message = lines[idx].strip()
            idx += 1

            # Parse author date
            # Python 3.10's fromisoformat() doesn't support timezone offsets
            # at all (e.g. "+00:00"). Fall back to strptime which works on
            # all Python versions.
            author_date = _parse_author_date(date_str)
            if author_date is None:
                continue

            # Collect shortstat lines until next commit (40-char hex SHA)
            # Git --format output is followed by a blank line, then --shortstat,
            # then another blank line before the next commit.
            insertions = 0
            deletions = 0
            while idx < n:
                line = lines[idx].strip()
                # Check if this is the start of the next commit (40-char hex SHA)
                if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
                    break
                # Check for shortstat content
                ins_match = _INSERTIONS_RE.search(line)
                del_match = _DELETIONS_RE.search(line)
                if ins_match:
                    insertions = int(ins_match.group(1))
                if del_match:
                    deletions = int(del_match.group(1))
                idx += 1

            commits.append(
                {
                    "sha": sha,
                    "author_name": author_name,
                    "author_email": author_email,
                    "author_date": author_date,
                    "message": message,
                    "insertions": insertions,
                    "deletions": deletions,
                }
            )

        return commits

    # ------------------------------------------------------------------
    # Window and collection builders
    # ------------------------------------------------------------------

    def _build_window(
        self,
        observations: List[Observation],
        commits: List[Dict[str, Any]],
    ) -> ObservationWindow:
        """Build a single ObservationWindow from commit observations.

        Git log outputs newest-first, so commits[0] is latest and
        commits[-1] is oldest. We use oldest as start_boundary.
        """
        # Oldest commit = last in list (git log is newest-first)
        oldest_date = commits[-1]["author_date"].isoformat()
        newest_date = commits[0]["author_date"].isoformat()

        metrics_present = sorted({obs.metric_id for obs in observations})

        return ObservationWindow(
            window_id="w00",
            window_index=0,
            strategy="commit_count",
            start_boundary=oldest_date,
            end_boundary=newest_date,
            observations=observations,
            start_commit=commits[-1]["sha"],
            end_commit=commits[0]["sha"],
            metrics_present=metrics_present,
            metadata={"total_commits": str(len(commits))},
        )

    def _empty_collection(
        self,
        repo_id: str,
        seed: Optional[int],
    ) -> ObservationCollection:
        """Return an empty ObservationCollection for zero-commit case."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        analysis_payload = f"{repo_id}:empty:{now_iso}"
        analysis_id = hashlib.sha256(analysis_payload.encode()).hexdigest()[:16]
        _provenance = ObservationProvenance(
            extractor_id=self.EXTRACTOR_ID,
            extraction_timestamp=now_iso,
            seed=seed,
        )

        empty_window = ObservationWindow(
            window_id="w00",
            window_index=0,
            strategy="commit_count",
            start_boundary=now_iso,
            end_boundary=now_iso,
            observations=[],
            metadata={"total_commits": "0"},
        )

        return ObservationCollection(
            collection_id=generate_observation_id("commit", "empty", "M-02"),
            repository_id=repo_id,
            analysis_id=analysis_id,
            windows=[empty_window],
            total_observations=0,
            total_metrics=0,
            extraction_timestamp=now_iso,
            schema_version=ODSS_SCHEMA_VERSION,
        )
