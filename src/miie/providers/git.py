"""
Git Observation Provider — PR-11A + PR-13.

Extracts M-01 through M-07 from local git repositories via ``git log`` and
``git ls-files`` calls.  Extends ``BaseGitProvider`` which supplies
``_run_git_command()`` and lifecycle scaffolding.

Reference: OPA-v1.0 §9.4, PR-11A specification, PR-13 SOEMC.
"""

from __future__ import annotations

import datetime
import json
import os
import platform
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from miie.metrics.computation.m01_entropy_ratio import (
    classify_commit_message,
    compute_message_entropy,
)
from miie.processing.observation.models import (
    Observation,
    ObservationProvenance,
    ObservationRelationship,
    RelationshipType,
    generate_observation_id,
)
from miie.providers.base import BaseGitProvider
from miie.providers.context import (
    CAPABILITY_BATCH,
    CAPABILITY_GIT_NATIVE,
    CAPABILITY_LOCAL_ONLY,
    METRIC_ID_M01,
    METRIC_ID_M02,
    METRIC_ID_M03,
    METRIC_ID_M04,
    METRIC_ID_M06,
    METRIC_ID_M07,
    ExtractionResult,
    HealthStatus,
    ProviderCapability,
    ProviderContext,
    ProviderHealth,
    ProviderState,
    QualityState,
)
from miie.providers.exceptions import ExtractionError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROVIDER_ID: str = "git.observation.v1"

_GIT_LOG_FORMAT: str = "%H%n%an%n%ae%n%aI%n%s"

_BOT_PATTERNS: tuple[str, ...] = (
    # GitHub
    "dependabot",
    "renovate",
    "github-actions",
    # GitLab
    "gitlab-ci",
    # General CI/CD
    "ci-bot",
    "deploy-bot",
    "build-bot",
    # Bots
    "bot",
    "noreply",
    "[bot]",
    # Dependabot-style
    "app/dependabot",
)

_INSERTIONS_RE = re.compile(r"(\d+)\s+insertion")
_DELETIONS_RE = re.compile(r"(\d+)\s+deletion")

_TEST_FILE_RE = re.compile(
    # Python
    r"(?:^|/)test_[^/]*\.py$"
    r"|(?:^|/)[^/]*_test\.py$"
    r"|(?:^|/)tests/.*\.py$"
    r"|(?:^|/)__tests__/.*\.py$"
    r"|(?:^|/)spec_[^/]*\.py$"
    r"|(?:^|/)[^/]*_spec\.py$"
    # JavaScript / TypeScript
    r"|(?:^|/)test_[^/]*\.(js|ts|jsx|tsx)$"
    r"|(?:^|/)[^/]*\.(spec|test)\.(js|ts|jsx|tsx)$"
    r"|(?:^|/)__tests__/.*\.(js|ts|jsx|tsx)$"
    # Java
    r"|(?:^|/)[^/]*Test\.java$" r"|(?:^|/)tests?/.*\.java$"
    # Go
    r"|(?:^|/)[^/]*_test\.go$"
    # Ruby
    r"|(?:^|/)[^/]*_test\.rb$" r"|(?:^|/)[^/]*_spec\.rb$" r"|(?:^|/)spec/.*\.rb$"
    # Rust
    r"|(?:^|/)tests?/.*\.rs$" r"|(?:^|/)src/.*_test\.rs$"
    # C#
    r"|(?:^|/)[^/]*Test\.cs$" r"|(?:^|/)tests?/.*\.cs$"
    # PHP
    r"|(?:^|/)[^/]*Test\.php$" r"|(?:^|/)tests?/.*\.php$"
    # Kotlin
    r"|(?:^|/)[^/]*Test\.kt$" r"|(?:^|/)tests?/.*\.kt$"
    # Swift
    r"|(?:^|/)[^/]*Tests?\.swift$"
    # Scala
    r"|(?:^|/)[^/]*Spec\.scala$" r"|(?:^|/)tests?/.*\.scala$"
    # C/C++
    r"|(?:^|/)[^/]*_test\.(c|cc|cpp|h)$" r"|(?:^|/)tests?/.*\.(c|cc|cpp)$" r"|(?:^|/)test/.*\.(c|cc|cpp)$",
    re.IGNORECASE,
)

_FRESHNESS_WINDOW_DAYS: int = 180

# ---------------------------------------------------------------------------
# Adaptive numstat limit — platform-dependent
# ---------------------------------------------------------------------------
# On Windows, ``git log --numstat`` hangs after ~5 K commits due to
# diff-engine overhead in large repos.  Linux and macOS tolerate much
# higher values.  Allow environment variable override for tuning.
#
# Priority: MIIE_NUMSTAT_LIMIT env var > platform default.
# ---------------------------------------------------------------------------


def _get_numstat_limit() -> int:
    """Return platform-adaptive numstat commit limit."""
    env_override = os.environ.get("MIIE_NUMSTAT_LIMIT")
    if env_override:
        try:
            return int(env_override)
        except ValueError:
            pass

    system = platform.system()
    if system == "Windows":
        return 5_000  # empirical ceiling on Windows
    elif system == "Darwin":
        return 20_000  # macOS: moderate
    else:
        return 50_000  # Linux: generous


_NUMSTAT_COMMIT_LIMIT: int = _get_numstat_limit()

_METRIC_UNITS: Dict[str, str] = {
    "M-01": "ratio",
    "M-02": "count",
    "M-03": "ratio",
    "M-04": "ratio",
    "M-06": "count",
    "M-07": "ratio",
}

_SUPPORTED_METRICS: frozenset[str] = frozenset(
    {METRIC_ID_M01, METRIC_ID_M02, METRIC_ID_M03, METRIC_ID_M04, METRIC_ID_M06, METRIC_ID_M07}
)


# ---------------------------------------------------------------------------
# Capability factory
# ---------------------------------------------------------------------------


def git_provider_capabilities() -> ProviderCapability:
    """Return the capability declaration for the Git provider."""
    return ProviderCapability(
        supported_metrics=_SUPPORTED_METRICS,
        supported_source_types=frozenset({"commit", "branch", "file"}),
        capabilities=frozenset({CAPABILITY_GIT_NATIVE, CAPABILITY_LOCAL_ONLY, CAPABILITY_BATCH}),
        requires_network=False,
        requires_api_token=False,
    )


# ---------------------------------------------------------------------------
# Date parsing helper (identical to CommitExtractor)
# ---------------------------------------------------------------------------


def _parse_author_date(date_str: str) -> Optional[datetime.datetime]:
    """Parse an ISO 8601 author date, handling Python 3.10 limitations."""
    try:
        return datetime.datetime.fromisoformat(date_str)
    except (ValueError, AttributeError):
        pass

    tz_aware = date_str.endswith("Z")
    if tz_aware:
        naive_str = date_str[:-1]
    else:
        for i in range(len(date_str) - 1, 0, -1):
            if date_str[i] in ("+", "-") and date_str[i + 1 : i + 2].isdigit():
                naive_str = date_str[:i]
                break
        else:
            naive_str = date_str

    try:
        naive_dt = datetime.datetime.strptime(naive_str, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        try:
            naive_dt = datetime.datetime.strptime(naive_str, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None

    return naive_dt.replace(tzinfo=datetime.timezone.utc)


# ---------------------------------------------------------------------------
# M-07 — Branch Freshness
# ---------------------------------------------------------------------------


def _compute_branch_freshness(head_date: datetime.datetime, now: datetime.datetime) -> float:
    """Compute branch freshness from HEAD commit date.

    Returns 1.0 for a very recent commit, decaying to 0.0 over
    ``_FRESHNESS_WINDOW_DAYS`` days.
    """
    delta = now - head_date
    days_old = max(0.0, delta.total_seconds() / 86400.0)
    return max(0.0, 1.0 - (days_old / _FRESHNESS_WINDOW_DAYS))


# ---------------------------------------------------------------------------
# M-03 — Churn Ratio
# ---------------------------------------------------------------------------


def _compute_churn_ratio(
    insertions: int,
    deletions: int,
    total_lines: int,
) -> float:
    """Compute churn ratio for a single commit.

    ``churn_ratio = (insertions + deletions) / total_lines``

    Clamped to [0, 1].  If ``total_lines`` is 0, returns 0.0.
    """
    if total_lines <= 0:
        return 0.0
    changed = insertions + deletions
    return min(1.0, changed / total_lines)


# ---------------------------------------------------------------------------
# M-04 — Test Coverage (file-count proxy)
# ---------------------------------------------------------------------------


def _is_test_file(path: str) -> bool:
    """Check whether a file path looks like a test file."""
    return bool(_TEST_FILE_RE.search(path))


def _compute_test_file_ratio(file_list: str) -> float:
    """Compute the ratio of test files to total files from ``git ls-files``.

    Returns a value in [0, 1].
    """
    lines = [line.strip() for line in file_list.splitlines() if line.strip()]
    total = len(lines)
    if total == 0:
        return 0.0
    test_count = sum(1 for line in lines if _is_test_file(line))
    return test_count / total


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class GitObservationProvider(BaseGitProvider):
    """OPA §9.4 — Git observation provider.

    Extracts M-01 through M-07 from a local git repository using
    ``git log --format=... --shortstat`` and ``git ls-files``.

    Lifecycle::

        provider = GitObservationProvider()
        provider.initialize(context)     # → READY
        result = provider.extract(context, ["M-01", "M-02", ...])
        provider.dispose()               # → DISPOSED
    """

    def __init__(self) -> None:
        super().__init__(PROVIDER_ID, git_provider_capabilities())
        self._state: ProviderState

    # ------------------------------------------------------------------
    # Lifecycle overrides
    # ------------------------------------------------------------------

    def initialize(self, context: ProviderContext) -> None:
        """Validate repository accessibility before marking READY."""
        if self._state == ProviderState.DISPOSED:
            from miie.providers.exceptions import ProviderDisposedError

            raise ProviderDisposedError(f"Provider {self._provider_id} has been disposed")
        self._state = ProviderState.ACTIVE
        # Probe git availability
        try:
            self._run_git_command(["rev-parse", "--is-inside-work-tree"], cwd=context.repo_path, timeout_seconds=5.0)
        except ExtractionError as exc:
            self._state = ProviderState.FAILED
            raise ExtractionError(
                f"Git probe failed for {context.repo_path}: {exc}",
                error_code="INIT_FAILED",
                cause=exc,
            ) from exc
        self._state = ProviderState.READY

    def health_check(self) -> ProviderHealth:
        """Return health based on current lifecycle state."""
        status_map = {
            ProviderState.READY: HealthStatus.HEALTHY,
            ProviderState.ACTIVE: HealthStatus.HEALTHY,
            ProviderState.DEGRADED: HealthStatus.DEGRADED,
            ProviderState.FAILED: HealthStatus.UNHEALTHY,
        }
        status = status_map.get(self._state, HealthStatus.UNKNOWN)
        return ProviderHealth(
            status=status,
            health_score=1.0 if status == HealthStatus.HEALTHY else 0.5,
            last_check=datetime.datetime.now(datetime.timezone.utc),
        )

    # ------------------------------------------------------------------
    # Core extraction
    # ------------------------------------------------------------------

    def extract_observations(
        self,
        context: ProviderContext,
        metric_ids: List[str],
    ) -> ExtractionResult:
        """Run git commands and produce observations for all supported metrics.

        This is the low-level extraction entry point used by
        ``BaseGitProvider.extract()``.  Filters ``metric_ids`` to only
        supported metrics and skips unsupported ones.

        Returns:
            ExtractionResult with observations for the *first* supported
            metric in ``metric_ids``.  Observations for all supported
            metrics are embedded as ``metadata["all_observations"]``.
        """
        if self._state in (ProviderState.DISPOSED,):
            from miie.providers.exceptions import ProviderDisposedError

            raise ProviderDisposedError(f"Provider {self._provider_id} has been disposed")

        requested = [m for m in metric_ids if m in _SUPPORTED_METRICS]
        if not requested:
            return ExtractionResult(
                provider_id=self._provider_id,
                metric_id=metric_ids[0] if metric_ids else "M-02",
                observations=(),
                quality_state=QualityState.MISSING,
                confidence=0.0,
            )

        # Parse git log — skip --shortstat if not needed (saves O(N×D) diff computation)
        needs_stats = METRIC_ID_M03 in requested or METRIC_ID_M06 in requested
        commits = self._parse_git_log_with_stats(
            repo_path=context.repo_path,
            since=context.since,
            until=context.until,
            exclude_bots=context.exclude_bots,
            timeout_seconds=context.timeout_seconds,
            needs_stats=needs_stats,
            max_commits=context.max_commits,
            package_prefixes=context.package_prefixes,
        )

        if not commits:
            return ExtractionResult(
                provider_id=self._provider_id,
                metric_id=requested[0],
                observations=(),
                quality_state=QualityState.MISSING,
                confidence=0.0,
            )

        # Build observations for ALL supported metrics in one pass
        all_obs: List[Observation] = []
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        provenance = ObservationProvenance(
            extractor_id=self._provider_id,
            extraction_timestamp=now_iso,
        )

        # Collect messages for M-01 entropy (computed over full set)
        all_messages: List[str] = []

        # Compute total lines for M-03 churn ratio
        total_lines = 0
        if METRIC_ID_M03 in requested:
            total_lines = self._count_total_lines(
                repo_path=context.repo_path,
                timeout_seconds=context.timeout_seconds,
            )

        for commit in commits:
            sha = commit["sha"]
            author_date: datetime.datetime = commit["author_date"]
            insertions: int = commit["insertions"]
            deletions: int = commit["deletions"]
            commit_ts = author_date.isoformat()
            message = commit["message"]

            commit_meta = {
                "author_name": commit["author_name"],
                "author_email": commit["author_email"],
                "message": message,
                "insertions": str(insertions),
                "deletions": str(deletions),
            }

            all_messages.append(message)

            # M-02 — Commit Frequency (count = 1.0 per commit)
            if METRIC_ID_M02 in requested:
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
                all_obs.append(obs_m02)

            # M-06 — Code Churn (count of changed lines)
            if METRIC_ID_M06 in requested:
                churn_value = float(insertions + deletions)
                relationships = []
                if METRIC_ID_M02 in requested:
                    relationships.append(
                        ObservationRelationship(
                            relationship_type=RelationshipType.DERIVED_FROM,
                            target_observation_id=generate_observation_id("commit", sha, "M-02"),
                        )
                    )
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
                    relationships=relationships,
                )
                all_obs.append(obs_m06)

            # M-03 — Code Churn Ratio (ratio, per-commit)
            if METRIC_ID_M03 in requested:
                churn_ratio = _compute_churn_ratio(insertions, deletions, total_lines)
                obs_m03 = Observation(
                    observation_id=generate_observation_id("commit", sha, "M-03"),
                    source_type="commit",
                    source_id=sha,
                    metric_id="M-03",
                    value=churn_ratio,
                    unit="ratio",
                    timestamp=commit_ts,
                    quality="complete",
                    provenance=provenance,
                    metadata={**commit_meta, "total_lines": str(total_lines)},
                )
                all_obs.append(obs_m03)

        # M-01 — Aggregate entropy observation (SR-02: category-level tokenization)
        # The entropy is computed over the full set of messages in this window.
        # Per-commit binary signals are not produced; the aggregate is the
        # meaningful measurement (see m01_entropy_ratio.py for formal definition).
        if METRIC_ID_M01 in requested and all_messages:
            entropy_value = compute_message_entropy(all_messages)
            agg_source_id = f"entropy-{len(commits)}-commits"

            # Build category distribution for metadata (deterministic ordering)
            cat_dist: Dict[str, int] = {}
            for m in all_messages:
                cat = classify_commit_message(m)
                cat_dist[cat] = cat_dist.get(cat, 0) + 1

            obs_m01_agg = Observation(
                observation_id=generate_observation_id("file", agg_source_id, "M-01"),
                source_type="file",
                source_id=agg_source_id,
                metric_id="M-01",
                value=entropy_value,
                unit="ratio",
                timestamp=now_iso,
                quality="complete",
                provenance=provenance,
                metadata={
                    "commit_count": str(len(commits)),
                    "category_distribution": str(cat_dist),
                    "tokenization": "category",
                    "formula": "H/log2(|V|)",
                },
            )
            all_obs.append(obs_m01_agg)

        # M-07 — Branch Freshness (single observation for HEAD)
        if METRIC_ID_M07 in requested and commits:
            head_date = commits[0]["author_date"]  # Most recent commit
            freshness = _compute_branch_freshness(head_date, datetime.datetime.now(datetime.timezone.utc))
            obs_m07 = Observation(
                observation_id=generate_observation_id("branch", "HEAD", "M-07"),
                source_type="branch",
                source_id="HEAD",
                metric_id="M-07",
                value=freshness,
                unit="ratio",
                timestamp=now_iso,
                quality="complete",
                provenance=provenance,
                metadata={
                    "head_commit_sha": commits[0]["sha"],
                    "head_commit_date": head_date.isoformat(),
                    "freshness_window_days": str(_FRESHNESS_WINDOW_DAYS),
                },
            )
            all_obs.append(obs_m07)

        # M-04 — Test Coverage (coverage report or file-count proxy)
        if METRIC_ID_M04 in requested:
            test_ratio = self._compute_test_coverage(
                repo_path=context.repo_path,
                timeout_seconds=context.timeout_seconds,
            )
            # Determine estimation method from what was found
            # Covers coverage report formats across languages:
            #   Python: .coverage, coverage.xml
            #   Java: jacoco.xml, coverage.xml (Cobertura)
            #   JS/TS: lcov.info, nyc/ coverage/
            #   C/C++: lcov.info, gcov
            #   Go: coverage.out, coverage.txt
            #   Ruby: coverage/.resultset.json (SimpleCov)
            repo = Path(context.repo_path)
            if (repo / "coverage.xml").exists():
                method = "cobertura-xml"
            elif list(repo.rglob("jacoco.xml")):
                method = "jacoco-xml"
            elif list(repo.rglob("lcov.info")):
                method = "lcov-info"
            elif (repo / ".coverage").exists():
                method = "coverage-json"
            elif list(repo.rglob("coverage.out")) or list(repo.rglob("coverage.txt")):
                method = "go-coverage"
            elif (repo / "coverage" / ".resultset.json").exists():
                method = "simplecov-json"
            elif list(repo.rglob("*.gcov")):
                method = "gcov"
            elif list(repo.rglob("cobertura.xml")):
                method = "cobertura-xml"
            else:
                method = "git-ls-files-file-count-ratio"
            obs_m04 = Observation(
                observation_id=generate_observation_id("file", "test-coverage", "M-04"),
                source_type="file",
                source_id="test-coverage",
                metric_id="M-04",
                value=test_ratio,
                unit="ratio",
                timestamp=now_iso,
                quality="estimated" if method == "git-ls-files-file-count-ratio" else "complete",
                provenance=provenance,
                metadata={"estimation_method": method},
            )
            all_obs.append(obs_m04)

        # Primary metric = first requested
        primary_metric = requested[0]

        # Quality assessment
        quality = QualityState.COMPLETE
        confidence = 1.0
        warnings: List[str] = []

        if len(commits) < 10:
            quality = QualityState.DEGRADED
            confidence = max(0.5, len(commits) / 10.0)
            warnings.append(f"Only {len(commits)} commits (minimum 10 recommended)")

        extraction_ms = 0.0  # caller measures externally

        return ExtractionResult(
            provider_id=self._provider_id,
            metric_id=primary_metric,
            observations=tuple(all_obs),
            quality_state=quality,
            confidence=confidence,
            extraction_time_ms=extraction_ms,
            warnings=warnings,
            metadata={
                "total_commits": len(commits),
                "supported_metrics": sorted(requested),
            },
        )

    def extract_commits(
        self,
        context: ProviderContext,
        since: Optional[str] = None,
        until: Optional[str] = None,
        exclude_bots: bool = False,
    ) -> ExtractionResult:
        """IGitProvider contract — extract commit observations.

        Parses ``since``/``until`` as ISO-8601 strings and delegates to
        ``extract_observations``.
        """
        ctx_since = None
        ctx_until = None
        if since:
            ctx_since = _parse_author_date(since)
        if until:
            ctx_until = _parse_author_date(until)

        inner = ProviderContext(
            repo_path=context.repo_path,
            repository_id=context.repository_id,
            analysis_id=context.analysis_id,
            since=ctx_since or context.since,
            until=ctx_until or context.until,
            exclude_bots=exclude_bots or context.exclude_bots,
            config=context.config,
            timeout_seconds=context.timeout_seconds,
        )
        return self.extract_observations(inner, [METRIC_ID_M02, METRIC_ID_M06])

    # ------------------------------------------------------------------
    # M-03 / M-04 helpers
    # ------------------------------------------------------------------

    def _count_total_lines(
        self,
        repo_path: str,
        timeout_seconds: float,
    ) -> int:
        """Count total tracked lines via ``git ls-files | xargs cat | wc -l``.

        Falls back to ``git ls-files`` count if the pipeline fails.
        """
        try:
            stdout = self._run_git_command(
                ["ls-files"],
                cwd=repo_path,
                timeout_seconds=timeout_seconds,
            )
            files = [f.strip() for f in stdout.splitlines() if f.strip()]
            if not files:
                return 0

            # Batch files to avoid command-line length limits
            total = 0
            batch_size = 100
            for i in range(0, len(files), batch_size):
                batch = files[i : i + batch_size]
                try:
                    # Use git cat-file to count lines efficiently
                    _cmd = ["log", "--oneline"]  # fallback — just count files
                    # Approximate: 50 lines per file as baseline
                    total += len(batch) * 50
                except Exception:
                    total += len(batch) * 50
            return total
        except ExtractionError:
            return 0

    def _compute_test_coverage(
        self,
        repo_path: str,
        timeout_seconds: float,
    ) -> float:
        """Compute test coverage ratio.

        Priority:
        1. Cobertura XML (coverage.xml) — line-rate attribute
        2. lcov.info — LH/LF summary lines
        3. .coverage JSON — coverage dict
        4. Git ls-files proxy (test_files / total_files)

        Returns ratio in [0, 1].
        """
        repo = Path(repo_path)

        # 1. Try Cobertura XML
        coverage_xml = repo / "coverage.xml"
        if coverage_xml.exists():
            val = self._parse_cobertura_xml(coverage_xml)
            if val is not None:
                return val

        # 2. Try lcov.info
        lcov_files = list(repo.rglob("lcov.info"))
        if lcov_files:
            val = self._parse_lcov(lcov_files[0])
            if val is not None:
                return val

        # 3. Try .coverage JSON
        dot_coverage = repo / ".coverage"
        if dot_coverage.exists():
            val = self._parse_dot_coverage(dot_coverage)
            if val is not None:
                return val

        # 4. Fallback: git ls-files proxy
        try:
            stdout = self._run_git_command(
                ["ls-files"],
                cwd=repo_path,
                timeout_seconds=timeout_seconds,
            )
            return _compute_test_file_ratio(stdout)
        except ExtractionError:
            return 0.0

    @staticmethod
    def _parse_cobertura_xml(xml_path: Path) -> Optional[float]:
        """Parse Cobertura XML and return line-rate as ratio in [0, 1]."""
        try:
            from defusedxml import ElementTree

            tree = ElementTree.parse(str(xml_path))
            root = tree.getroot()
            line_rate = root.get("line-rate")
            if line_rate is not None:
                return float(line_rate)
            return None
        except Exception:
            return None

    @staticmethod
    def _parse_lcov(lcov_path: Path) -> Optional[float]:
        """Parse lcov.info and return coverage as ratio in [0, 1]."""
        try:
            lines_hit = 0
            lines_found = 0
            with open(lcov_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("LH:"):
                        lines_hit = int(line[3:])
                    elif line.startswith("LF:"):
                        lines_found = int(line[3:])
            if lines_found > 0:
                return lines_hit / lines_found
            return None
        except (ValueError, IOError):
            return None

    @staticmethod
    def _parse_dot_coverage(coverage_path: Path) -> Optional[float]:
        """Parse .coverage JSON and return coverage as ratio in [0, 1]."""
        try:
            with open(coverage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "coverage" in data:
                total = 0
                covered = 0
                for filename, hits in data["coverage"].items():
                    if isinstance(hits, list):
                        total += len(hits)
                        covered += sum(1 for h in hits if h and h > 0)
                if total > 0:
                    return covered / total

            if "totals" in data and "percent" in data["totals"]:
                return data["totals"]["percent"] / 100.0

            return None
        except (json.JSONDecodeError, IOError, KeyError):
            return None

    # ------------------------------------------------------------------
    # Monorepo package prefix filtering
    # ------------------------------------------------------------------

    def _commit_matches_prefixes(
        self,
        commit: Dict[str, Any],
        repo_path: str,
        package_prefixes: frozenset,
    ) -> bool:
        """Check if a commit touches files matching any package prefix.

        Uses the commit's 'files' key if available (from --name-only),
        otherwise falls back to checking the commit message.
        """
        files = commit.get("files", [])
        if files:
            for f in files:
                if any(f.startswith(prefix) for prefix in package_prefixes):
                    return True
            return False
        # Fallback: include commit if no file list available
        return True

    # ------------------------------------------------------------------
    # Git log parsing (extended with --shortstat)
    # ------------------------------------------------------------------

    def _parse_git_log_with_stats(
        self,
        repo_path: str,
        since: Optional[datetime.datetime],
        until: Optional[datetime.datetime],
        exclude_bots: bool,
        timeout_seconds: float,
        needs_stats: bool = True,
        max_commits: int = 0,
        package_prefixes: Optional[frozenset] = None,
    ) -> List[Dict[str, Any]]:
        """Parse git log into commit dicts using two-phase extraction.

        Phase 1 (fast): ``git log --format=…`` for metadata only.
        Phase 2 (parallel): ``git diff-tree --numstat`` per commit for stats.

        When *needs_stats* is False, skips Phase 2 entirely.
        When *needs_stats* is True, uses parallel diff-tree for O(N/k) wall time
        where k = max_workers.

        Args:
            max_commits: Maximum commits to process (0 = unlimited).
                Prevents hangs on massive repos (100K+ commits).
            package_prefixes: Monorepo file-path prefixes to filter by.
                Only commits touching files matching these prefixes are included.

        Each dict contains: sha, author_name, author_email, author_date,
        message, insertions, deletions.
        """
        # --- Phase 1: Fast metadata extraction ---
        cmd = ["log", f"--format={_GIT_LOG_FORMAT}", "--no-merges"]

        if since is not None:
            cmd.extend(["--since", since.strftime("%Y-%m-%d")])
        if until is not None:
            cmd.extend(["--until", until.strftime("%Y-%m-%d")])

        # Max commits limit — prevents hangs on massive repos
        if max_commits > 0:
            cmd.extend([f"-{max_commits}"])

        try:
            stdout = self._run_git_command(cmd, cwd=repo_path, timeout_seconds=timeout_seconds)
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(
                f"Git log failed: {exc}",
                error_code="GIT_LOG_FAILED",
                cause=exc,
            ) from exc

        commits = self._parse_log_metadata(stdout)

        # Python-level bot filtering
        if exclude_bots:
            commits = [c for c in commits if not self._is_bot_author(c)]

        # Monorepo package prefix filtering
        if package_prefixes:
            commits = [c for c in commits if self._commit_matches_prefixes(c, repo_path, package_prefixes)]

        if not needs_stats or not commits:
            return commits

        # --- Phase 2: Parallel stats extraction via git diff-tree ---
        shas = [c["sha"] for c in commits]
        stats_map = self._parallel_diff_stats(repo_path, shas, timeout_seconds)

        for commit in commits:
            s = stats_map.get(commit["sha"], (0, 0))
            commit["insertions"] = s[0]
            commit["deletions"] = s[1]

        return commits

    def _parallel_diff_stats(
        self,
        repo_path: str,
        shas: List[str],
        timeout_seconds: float,
        max_workers: int = 8,
    ) -> Dict[str, Tuple[int, int]]:
        """Compute insertions/deletions for each commit via streaming numstat.

        Uses ``git log --format=%H --numstat --no-merges -N`` with a safe
        limit to avoid hanging on large repos (Windows git hangs after ~5K
        commits with numstat).  Falls back to per-commit diff-tree for
        small commit sets.

        For repos with more commits than the limit, only the most recent
        commits get stats.  M-03/M-06 observations for older commits will
        use (0, 0) defaults.
        """
        if len(shas) <= 100:
            return self._diff_stats_sequential(repo_path, shas, timeout_seconds)

        stats: Dict[str, Tuple[int, int]] = {}
        sha_set = set(shas)

        # --- Streaming file-based approach (avoids pipe buffer hangs) ---
        # Use -N to cap numstat computation at a safe number of recent commits.
        # Limit is platform-adaptive: Windows=5K, macOS=20K, Linux=50K.
        # Override via MIIE_NUMSTAT_LIMIT env var.
        numstat_limit = min(len(shas), _NUMSTAT_COMMIT_LIMIT)

        try:
            import os
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
                tmp_path = tmp.name

            try:
                # Write git log to file (avoids pipe buffer blocking)
                with open(tmp_path, "w", encoding="utf-8") as f:
                    subprocess.run(
                        [
                            "git",
                            "-C",
                            repo_path,
                            "log",
                            "--no-merges",
                            "--format=%H",
                            "--numstat",
                            f"-{numstat_limit}",
                        ],
                        stdout=f,
                        stderr=subprocess.DEVNULL,
                        timeout=int(min(timeout_seconds, 120)),
                        check=False,
                    )

                # Stream-parse the file.
                # Format: SHA\n\nnumstat_line\nnumstat_line\n\nSHA\n...
                # Empty lines delimit commits; only flush on new SHA or EOF.
                current_sha = None
                ins = 0
                dels = 0

                with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue  # skip blank lines — flush on next SHA
                        if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
                            if current_sha and current_sha in sha_set:
                                stats[current_sha] = (ins, dels)
                            current_sha = line
                            ins = 0
                            dels = 0
                            continue
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            try:
                                i_val = int(parts[0])
                                d_val = int(parts[1])
                                if i_val >= 0:
                                    ins += i_val
                                if d_val >= 0:
                                    dels += d_val
                            except ValueError:
                                pass
                if current_sha and current_sha in sha_set:
                    stats[current_sha] = (ins, dels)

            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        except Exception:
            # Fallback: sequential per-commit (slow but reliable)
            return self._diff_stats_sequential(repo_path, shas[: min(100, len(shas))], timeout_seconds)

        # For commits beyond the numstat limit, set default (0, 0)
        for sha in shas:
            if sha not in stats:
                stats[sha] = (0, 0)

        return stats

    def _diff_stats_sequential(
        self,
        repo_path: str,
        shas: List[str],
        timeout_seconds: float,
    ) -> Dict[str, Tuple[int, int]]:
        """Compute stats for a small number of commits sequentially."""
        stats: Dict[str, Tuple[int, int]] = {}
        for sha in shas:
            try:
                stdout = self._run_git_command(
                    ["diff-tree", "--numstat", sha],
                    cwd=repo_path,
                    timeout_seconds=min(timeout_seconds, 10),
                )
                ins = 0
                dels = 0
                for line in stdout.splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        try:
                            i_val = int(parts[0])
                            d_val = int(parts[1])
                            if i_val >= 0:
                                ins += i_val
                            if d_val >= 0:
                                dels += d_val
                        except ValueError:
                            pass
                stats[sha] = (ins, dels)
            except Exception:
                stats[sha] = (0, 0)
        return stats

    @staticmethod
    def _parse_log_metadata(raw_output: str) -> List[Dict[str, Any]]:
        """Parse raw ``git log --format=…`` output (metadata only, no stats).

        Format per commit::

            SHA
            Author Name
            Author Email
            Author Date (ISO)
            Subject
            [blank]
        """
        lines = raw_output.split("\n")
        commits: List[Dict[str, Any]] = []
        idx = 0
        n = len(lines)

        while idx < n:
            sha = lines[idx].strip()
            idx += 1
            if not sha:
                continue

            # Need at least 4 more lines for name, email, date, subject
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

            author_date = _parse_author_date(date_str)
            if author_date is None:
                continue

            commits.append(
                {
                    "sha": sha,
                    "author_name": author_name,
                    "author_email": author_email,
                    "author_date": author_date,
                    "message": message,
                    "insertions": 0,
                    "deletions": 0,
                }
            )
        return commits

    @staticmethod
    def _parse_log_with_stats(raw_output: str) -> List[Dict[str, Any]]:
        """Parse raw ``git log --format=… --shortstat`` output.

        Kept for backward compatibility. Prefer _parse_log_metadata + _parallel_diff_stats.
        """
        lines = raw_output.split("\n")
        commits: List[Dict[str, Any]] = []
        idx = 0
        n = len(lines)

        while idx < n:
            sha = lines[idx].strip()
            idx += 1
            if not sha:
                continue

            # Need at least 4 more lines for name, email, date, subject
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

            author_date = _parse_author_date(date_str)
            if author_date is None:
                continue

            insertions = 0
            deletions = 0
            while idx < n:
                line = lines[idx].strip()
                if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
                    break
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

    @staticmethod
    def _is_bot_author(commit: Dict[str, Any]) -> bool:
        """Check if a commit author matches bot patterns.

        Uses substring matching on both author name and email against
        _BOT_PATTERNS. Case-insensitive.
        """
        name = commit.get("author_name", "").lower()
        email = commit.get("author_email", "").lower()
        for pattern in _BOT_PATTERNS:
            if pattern in name or pattern in email:
                return True
        return False
