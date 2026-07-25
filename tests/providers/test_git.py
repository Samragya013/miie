"""Tests for miie.providers.git module — GitObservationProvider."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

from miie.metrics.computation.m01_entropy_ratio import (
    classify_commit_message,
    compute_message_entropy,
)
from miie.processing.observation.models import (
    ObservationProvenance,
    generate_observation_id,
)
from miie.providers.context import (
    HealthStatus,
    ProviderCapability,
    ProviderContext,
    ProviderState,
    QualityState,
)
from miie.providers.exceptions import ExtractionError, ProviderDisposedError
from miie.providers.git import (
    PROVIDER_ID,
    GitObservationProvider,
    _compute_branch_freshness,
    _compute_churn_ratio,
    _compute_test_file_ratio,
    _is_test_file,
    _parse_author_date,
    git_provider_capabilities,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(
    repo_path: str = "/tmp/repo",
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    exclude_bots: bool = False,
) -> ProviderContext:
    return ProviderContext(
        repo_path=repo_path,
        repository_id="test-repo",
        analysis_id="test-analysis",
        since=since,
        until=until,
        exclude_bots=exclude_bots,
    )


_SAMPLE_GIT_LOG = (
    "aaa1111111111111111111111111111111111111\n"
    "Alice\n"
    "alice@example.com\n"
    "2025-06-01T10:00:00+00:00\n"
    "feat: add feature\n"
    "\n"
    " 10 insertions(+), 5 deletions(-)\n"
    "\n"
    "bbb2222222222222222222222222222222222222\n"
    "Bob\n"
    "bob@example.com\n"
    "2025-06-02T11:00:00+00:00\n"
    "fix: bug fix\n"
    "\n"
    " 3 insertions(+), 2 deletions(-)\n"
    "\n"
)

_SAMPLE_GIT_LOG_META = (
    "aaa1111111111111111111111111111111111111\n"
    "Alice\n"
    "alice@example.com\n"
    "2025-06-01T10:00:00+00:00\n"
    "feat: add feature\n"
    "\n"
    "bbb2222222222222222222222222222222222222\n"
    "Bob\n"
    "bob@example.com\n"
    "2025-06-02T11:00:00+00:00\n"
    "fix: bug fix\n"
    "\n"
)

_SAMPLE_DIFF_STATS = {
    "aaa1111111111111111111111111111111111111": (10, 5),
    "bbb2222222222222222222222222222222222222": (3, 2),
}


@pytest.fixture
def provider() -> GitObservationProvider:
    return GitObservationProvider()


@pytest.fixture
def initialized_provider(provider: GitObservationProvider) -> GitObservationProvider:
    ctx = _make_context()
    with patch.object(provider, "_run_git_command", return_value="true"):
        provider.initialize(ctx)
    return provider


def _mock_extract(provider, sample_log=_SAMPLE_GIT_LOG_META, stats=None):
    """Context manager that mocks _run_git_command and _parallel_diff_stats."""
    if stats is None:
        stats = _SAMPLE_DIFF_STATS
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch.object(provider, "_run_git_command", return_value=sample_log))
    stack.enter_context(patch.object(provider, "_parallel_diff_stats", return_value=stats))
    return stack


# ---------------------------------------------------------------------------
# Capability tests
# ---------------------------------------------------------------------------


class TestGitProviderCapabilities:
    def test_capabilities_returns_provider_capability(self):
        caps = git_provider_capabilities()
        assert isinstance(caps, ProviderCapability)

    def test_supports_m01(self):
        caps = git_provider_capabilities()
        assert caps.supports_metric("M-01")

    def test_supports_m02(self):
        caps = git_provider_capabilities()
        assert caps.supports_metric("M-02")

    def test_supports_m03(self):
        caps = git_provider_capabilities()
        assert caps.supports_metric("M-03")

    def test_supports_m04(self):
        caps = git_provider_capabilities()
        assert caps.supports_metric("M-04")

    def test_supports_m06(self):
        caps = git_provider_capabilities()
        assert caps.supports_metric("M-06")

    def test_supports_m07(self):
        caps = git_provider_capabilities()
        assert caps.supports_metric("M-07")

    def test_does_not_support_m05(self):
        caps = git_provider_capabilities()
        assert not caps.supports_metric("M-05")

    def test_requires_no_network(self):
        caps = git_provider_capabilities()
        assert not caps.requires_network

    def test_requires_no_api_token(self):
        caps = git_provider_capabilities()
        assert not caps.requires_api_token

    def test_source_types_include_commit(self):
        caps = git_provider_capabilities()
        assert "commit" in caps.supported_source_types

    def test_source_types_include_branch(self):
        caps = git_provider_capabilities()
        assert "branch" in caps.supported_source_types

    def test_source_types_include_file(self):
        caps = git_provider_capabilities()
        assert "file" in caps.supported_source_types

    def test_capabilities_include_git_native(self):
        caps = git_provider_capabilities()
        assert "git-native" in caps.capabilities

    def test_capabilities_include_local_only(self):
        caps = git_provider_capabilities()
        assert "local-only" in caps.capabilities


# ---------------------------------------------------------------------------
# Provider identity and state tests
# ---------------------------------------------------------------------------


class TestGitProviderIdentity:
    def test_provider_id(self, provider: GitObservationProvider):
        assert provider.provider_id == PROVIDER_ID
        assert provider.provider_id == "git.observation.v1"

    def test_initial_state_is_uninitialized(self, provider: GitObservationProvider):
        assert provider.state == ProviderState.UNINITIALIZED

    def test_capabilities_property(self, provider: GitObservationProvider):
        caps = provider.get_capabilities()
        assert caps.supports_metric("M-02")
        assert caps.supports_metric("M-06")
        assert caps.supports_metric("M-01")
        assert caps.supports_metric("M-03")

    def test_supports_metric_delegates(self, provider: GitObservationProvider):
        assert provider.supports_metric("M-02")
        assert provider.supports_metric("M-06")
        assert provider.supports_metric("M-01")
        assert provider.supports_metric("M-03")
        assert not provider.supports_metric("M-05")


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


class TestGitProviderLifecycle:
    def test_initialize_sets_ready(self, provider: GitObservationProvider):
        ctx = _make_context()
        with patch.object(provider, "_run_git_command", return_value="true"):
            provider.initialize(ctx)
        assert provider.state == ProviderState.READY

    def test_initialize_probes_git(self, provider: GitObservationProvider):
        ctx = _make_context(repo_path="/some/repo")
        with patch.object(provider, "_run_git_command", return_value="true") as mock_run:
            provider.initialize(ctx)
        mock_run.assert_called_once_with(
            ["rev-parse", "--is-inside-work-tree"],
            cwd="/some/repo",
            timeout_seconds=5.0,
        )

    def test_initialize_sets_failed_on_error(self, provider: GitObservationProvider):
        ctx = _make_context()
        with patch.object(provider, "_run_git_command", side_effect=ExtractionError("git not found")):
            with pytest.raises(ExtractionError, match="Git probe failed"):
                provider.initialize(ctx)
        assert provider.state == ProviderState.FAILED

    def test_dispose_sets_disposed(self, initialized_provider: GitObservationProvider):
        initialized_provider.dispose()
        assert initialized_provider.state == ProviderState.DISPOSED

    def test_dispose_from_any_state(self, provider: GitObservationProvider):
        provider.dispose()
        assert provider.state == ProviderState.DISPOSED

    def test_initialize_after_dispose_raises(self, provider: GitObservationProvider):
        provider.dispose()
        ctx = _make_context()
        with pytest.raises(ProviderDisposedError):
            provider.initialize(ctx)


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------


class TestGitProviderHealth:
    def test_health_uninitialized(self, provider: GitObservationProvider):
        health = provider.health_check()
        assert health.status == HealthStatus.UNKNOWN

    def test_health_ready(self, initialized_provider: GitObservationProvider):
        health = initialized_provider.health_check()
        assert health.status == HealthStatus.HEALTHY
        assert health.health_score == 1.0

    def test_health_disposed(self, provider: GitObservationProvider):
        provider.dispose()
        health = provider.health_check()
        assert health.status == HealthStatus.UNKNOWN

    def test_health_failed(self, provider: GitObservationProvider):
        provider._state = ProviderState.FAILED
        health = provider.health_check()
        assert health.status == HealthStatus.UNHEALTHY
        assert health.health_score == 0.5

    def test_health_degraded(self, provider: GitObservationProvider):
        provider._state = ProviderState.DEGRADED
        health = provider.health_check()
        assert health.status == HealthStatus.DEGRADED


# ---------------------------------------------------------------------------
# Log parsing tests
# ---------------------------------------------------------------------------


class TestParseLogWithStats:
    def test_parse_two_commits(self):
        commits = GitObservationProvider._parse_log_with_stats(_SAMPLE_GIT_LOG)
        assert len(commits) == 2

    def test_parse_first_commit(self):
        commits = GitObservationProvider._parse_log_with_stats(_SAMPLE_GIT_LOG)
        c = commits[0]
        assert c["sha"] == "aaa1111111111111111111111111111111111111"
        assert c["author_name"] == "Alice"
        assert c["author_email"] == "alice@example.com"
        assert c["message"] == "feat: add feature"
        assert c["insertions"] == 10
        assert c["deletions"] == 5

    def test_parse_second_commit(self):
        commits = GitObservationProvider._parse_log_with_stats(_SAMPLE_GIT_LOG)
        c = commits[1]
        assert c["sha"] == "bbb2222222222222222222222222222222222222"
        assert c["author_name"] == "Bob"
        assert c["insertions"] == 3
        assert c["deletions"] == 2

    def test_parse_empty_output(self):
        commits = GitObservationProvider._parse_log_with_stats("")
        assert commits == []

    def test_parse_no_shortstat(self):
        log = (
            "aaa1111111111111111111111111111111111111\n"
            "Alice\n"
            "alice@example.com\n"
            "2025-06-01T10:00:00+00:00\n"
            "feat: add feature\n"
            "\n"
        )
        commits = GitObservationProvider._parse_log_with_stats(log)
        assert len(commits) == 1
        assert commits[0]["insertions"] == 0
        assert commits[0]["deletions"] == 0

    def test_parse_insertions_only(self):
        log = (
            "aaa1111111111111111111111111111111111111\n"
            "Alice\n"
            "alice@example.com\n"
            "2025-06-01T10:00:00+00:00\n"
            "feat: add\n"
            "\n"
            " 5 insertions(+)\n"
            "\n"
        )
        commits = GitObservationProvider._parse_log_with_stats(log)
        assert commits[0]["insertions"] == 5
        assert commits[0]["deletions"] == 0

    def test_parse_deletions_only(self):
        log = (
            "aaa1111111111111111111111111111111111111\n"
            "Alice\n"
            "alice@example.com\n"
            "2025-06-01T10:00:00+00:00\n"
            "refactor: cleanup\n"
            "\n"
            " 3 deletions(-)\n"
            "\n"
        )
        commits = GitObservationProvider._parse_log_with_stats(log)
        assert commits[0]["insertions"] == 0
        assert commits[0]["deletions"] == 3


# ---------------------------------------------------------------------------
# Date parsing tests
# ---------------------------------------------------------------------------


class TestParseAuthorDate:
    def test_valid_iso_with_tz(self):
        dt = _parse_author_date("2025-06-01T10:00:00+00:00")
        assert dt is not None
        assert dt.year == 2025

    def test_valid_iso_z_ending(self):
        dt = _parse_author_date("2025-06-01T10:00:00Z")
        assert dt is not None

    def test_valid_iso_no_tz(self):
        dt = _parse_author_date("2025-06-01T10:00:00")
        assert dt is not None

    def test_invalid_date_returns_none(self):
        dt = _parse_author_date("not-a-date")
        assert dt is None


# ---------------------------------------------------------------------------
# extract_observations tests
# ---------------------------------------------------------------------------


class TestExtractObservations:
    def test_extracts_m02_and_m06(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-02", "M-06"])

        assert result.provider_id == PROVIDER_ID
        assert result.observation_count == 4  # 2 commits × 2 metrics

    def test_extracts_only_m02(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-02"])

        assert result.observation_count == 2  # 2 commits × 1 metric
        for obs in result.observations:
            assert obs.metric_id == "M-02"

    def test_extracts_only_m06(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-06"])

        assert result.observation_count == 2
        for obs in result.observations:
            assert obs.metric_id == "M-06"

    def test_empty_repo_returns_missing(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with patch.object(
            initialized_provider,
            "_run_git_command",
            return_value="",
        ):
            result = initialized_provider.extract_observations(ctx, ["M-02", "M-06"])

        assert result.observation_count == 0
        assert result.quality_state == QualityState.MISSING
        assert result.confidence == 0.0

    def test_unsupported_metric_only(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-05"])

        assert result.observation_count == 0
        assert result.quality_state == QualityState.MISSING

    def test_mixed_supported_and_unsupported(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-05", "M-02", "M-04"])

        # M-02 produces 2 per-commit observations; M-04 produces 1 aggregate; M-05 produces 0
        assert result.observation_count == 3

    def test_low_commit_count_is_degraded(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        single_commit = (
            "aaa1111111111111111111111111111111111111\n"
            "Alice\n"
            "alice@example.com\n"
            "2025-06-01T10:00:00+00:00\n"
            "feat: add\n"
            "\n"
        )
        with patch.object(
            initialized_provider,
            "_run_git_command",
            return_value=single_commit,
        ):
            result = initialized_provider.extract_observations(ctx, ["M-02", "M-06"])

        assert result.quality_state == QualityState.DEGRADED
        assert result.confidence < 1.0
        assert len(result.warnings) == 1
        assert "1 commits" in result.warnings[0]

    def test_disposed_provider_raises(self, initialized_provider: GitObservationProvider):
        initialized_provider.dispose()
        ctx = _make_context()
        with pytest.raises(ProviderDisposedError):
            initialized_provider.extract_observations(ctx, ["M-02"])

    def test_m06_value_is_insertions_plus_deletions(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-06"])

        # First commit: 10 ins + 5 del = 15.0
        assert result.observations[0].value == 15.0
        # Second commit: 3 ins + 2 del = 5.0
        assert result.observations[1].value == 5.0

    def test_m02_value_is_one(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-02"])

        for obs in result.observations:
            assert obs.value == 1.0

    def test_metadata_contains_commit_count(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-02"])

        assert result.metadata["total_commits"] == 2

    def test_observations_have_provenance(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-02"])

        for obs in result.observations:
            assert isinstance(obs.provenance, ObservationProvenance)
            assert obs.provenance.extractor_id == PROVIDER_ID

    def test_observations_have_commit_metadata(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-02"])

        obs = result.observations[0]
        assert obs.metadata["author_name"] == "Alice"
        assert obs.metadata["author_email"] == "alice@example.com"

    def test_git_command_error_raises(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with patch.object(
            initialized_provider,
            "_run_git_command",
            side_effect=ExtractionError("git failed"),
        ):
            with pytest.raises(ExtractionError):
                initialized_provider.extract_observations(ctx, ["M-02"])


# ---------------------------------------------------------------------------
# extract_commits (IGitProvider contract) tests
# ---------------------------------------------------------------------------


class TestExtractCommits:
    def test_delegates_to_extract_observations(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_commits(ctx)

        assert result.observation_count == 4  # 2 commits × 2 metrics

    def test_passes_since_until(self, initialized_provider: GitObservationProvider):
        since = datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc)
        until = datetime.datetime(2025, 6, 30, tzinfo=datetime.timezone.utc)
        ctx = _make_context(since=since, until=until)
        with patch.object(initialized_provider, "_run_git_command", return_value=_SAMPLE_GIT_LOG_META) as mock_run:
            with patch.object(initialized_provider, "_parallel_diff_stats", return_value=_SAMPLE_DIFF_STATS):
                initialized_provider.extract_commits(ctx)

        call_args = mock_run.call_args
        assert call_args is not None

    def test_exclude_bots_propagates(self, initialized_provider: GitObservationProvider):
        ctx = _make_context(exclude_bots=True)
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_commits(ctx)

        assert result.observation_count == 4

    def test_custom_since_string(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_commits(ctx, since="2025-06-01T00:00:00+00:00")

        assert result.observation_count == 4


# ---------------------------------------------------------------------------
# Deterministic observation ID tests
# ---------------------------------------------------------------------------


class TestObservationIds:
    def test_m02_observation_ids_are_deterministic(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            r1 = initialized_provider.extract_observations(ctx, ["M-02"])
        with _mock_extract(initialized_provider):
            r2 = initialized_provider.extract_observations(ctx, ["M-02"])

        ids1 = [o.observation_id for o in r1.observations]
        ids2 = [o.observation_id for o in r2.observations]
        assert ids1 == ids2

    def test_m02_and_m06_have_different_ids(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-02", "M-06"])

        m02_ids = {o.observation_id for o in result.observations if o.metric_id == "M-02"}
        m06_ids = {o.observation_id for o in result.observations if o.metric_id == "M-06"}
        assert m02_ids.isdisjoint(m06_ids)

    def test_m06_has_derived_from_relationship(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-02", "M-06"])

        m06_obs = [o for o in result.observations if o.metric_id == "M-06"]
        for obs in m06_obs:
            assert len(obs.relationships) == 1
            assert obs.relationships[0].target_observation_id == generate_observation_id(
                "commit", obs.source_id, "M-02"
            )

    def test_m06_without_m02_has_no_relationships(self, initialized_provider: GitObservationProvider):
        ctx = _make_context()
        with _mock_extract(initialized_provider):
            result = initialized_provider.extract_observations(ctx, ["M-06"])

        for obs in result.observations:
            assert len(obs.relationships) == 0


# ---------------------------------------------------------------------------
# Registry integration smoke test
# ---------------------------------------------------------------------------


class TestRegistryIntegration:
    def test_provider_can_be_registered(self):
        from miie.providers.registry import ObservationProviderRegistry

        registry = ObservationProviderRegistry()
        provider = GitObservationProvider()
        caps = git_provider_capabilities()
        registry.register(provider, caps)
        discovered = registry.discover("M-02")
        assert any(p.provider_id == PROVIDER_ID for p in discovered)

    def test_provider_discovered_by_metric(self):
        from miie.providers.registry import ObservationProviderRegistry

        registry = ObservationProviderRegistry()
        provider = GitObservationProvider()
        caps = git_provider_capabilities()
        registry.register(provider, caps)
        entries = registry.get_by_metric("M-06")
        assert any(e.provider_id == PROVIDER_ID for e in entries)


# ---------------------------------------------------------------------------
# M-01 — Commit Entropy helper tests
# ---------------------------------------------------------------------------


class TestCommitEntropyHelpers:
    def test_classify_feat(self):
        assert classify_commit_message("feat: add login") == "feat"

    def test_classify_fix(self):
        assert classify_commit_message("fix: resolve crash") == "fix"

    def test_classify_docs(self):
        assert classify_commit_message("docs: update readme") == "docs"

    def test_classify_refactor(self):
        assert classify_commit_message("refactor: clean up") == "refactor"

    def test_classify_test(self):
        assert classify_commit_message("test: add unit tests") == "test"

    def test_classify_chore(self):
        assert classify_commit_message("chore: bump deps") == "chore"

    def test_classify_ci(self):
        assert classify_commit_message("ci: add workflow") == "ci"

    def test_classify_other(self):
        assert classify_commit_message("random message") == "other"

    def test_entropy_empty(self):
        assert compute_message_entropy([]) == 0.0

    def test_entropy_single_category(self):
        # All same category → entropy = 0
        msgs = ["feat: a", "feat: b", "feat: c"]
        assert compute_message_entropy(msgs) == 0.0

    def test_entropy_two_categories(self):
        # Two equal categories → entropy = 1.0 (max for 2 categories)
        msgs = ["feat: a", "feat: b", "fix: a", "fix: b"]
        assert abs(compute_message_entropy(msgs) - 1.0) < 0.01

    def test_entropy_diverse(self):
        # All 7 categories → high entropy
        msgs = [
            "feat: a",
            "fix: b",
            "docs: c",
            "refactor: d",
            "test: e",
            "chore: f",
            "ci: g",
        ]
        entropy = compute_message_entropy(msgs)
        assert entropy > 0.8  # Should be close to 1.0


# ---------------------------------------------------------------------------
# M-07 — Branch Freshness helper tests
# ---------------------------------------------------------------------------


class TestBranchFreshnessHelpers:
    def test_fresh_branch(self):
        import datetime

        now = datetime.datetime(2025, 7, 3, tzinfo=datetime.timezone.utc)
        head = datetime.datetime(2025, 7, 3, tzinfo=datetime.timezone.utc)
        assert _compute_branch_freshness(head, now) == 1.0

    def test_stale_branch(self):
        import datetime

        now = datetime.datetime(2025, 7, 3, tzinfo=datetime.timezone.utc)
        head = datetime.datetime(2025, 4, 1, tzinfo=datetime.timezone.utc)  # ~93 days old
        freshness = _compute_branch_freshness(head, now)
        assert 0.0 < freshness < 1.0

    def test_very_stale_branch(self):
        import datetime

        now = datetime.datetime(2025, 7, 3, tzinfo=datetime.timezone.utc)
        head = datetime.datetime(2024, 12, 1, tzinfo=datetime.timezone.utc)  # ~214 days old
        freshness = _compute_branch_freshness(head, now)
        assert freshness == 0.0


# ---------------------------------------------------------------------------
# M-03 — Churn Ratio helper tests
# ---------------------------------------------------------------------------


class TestChurnRatioHelpers:
    def test_zero_total_lines(self):
        assert _compute_churn_ratio(10, 5, 0) == 0.0

    def test_high_churn(self):
        # 150 changed / 100 total → clamped to 1.0
        assert _compute_churn_ratio(100, 50, 100) == 1.0

    def test_low_churn(self):
        assert _compute_churn_ratio(5, 5, 1000) == 0.01

    def test_no_changes(self):
        assert _compute_churn_ratio(0, 0, 1000) == 0.0


# ---------------------------------------------------------------------------
# M-04 — Test Coverage helper tests
# ---------------------------------------------------------------------------


class TestTestCoverageHelpers:
    def test_is_test_file_test_prefix(self):
        assert _is_test_file("tests/test_utils.py") is True

    def test_is_test_file_test_suffix(self):
        assert _is_test_file("src/utils_test.py") is True

    def test_is_test_file_spec_prefix(self):
        assert _is_test_file("spec_helper.py") is True

    def test_is_test_file_not_test(self):
        assert _is_test_file("src/main.py") is False

    def test_compute_ratio_empty(self):
        assert _compute_test_file_ratio("") == 0.0

    def test_compute_ratio_no_tests(self):
        file_list = "src/main.py\nsrc/utils.py\nsrc/config.py"
        assert _compute_test_file_ratio(file_list) == 0.0

    def test_compute_ratio_all_tests(self):
        file_list = "test_a.py\ntest_b.py\ntest_c.py"
        assert _compute_test_file_ratio(file_list) == 1.0

    def test_compute_ratio_mixed(self):
        file_list = "src/main.py\ntest_main.py\nsrc/utils.py"
        ratio = _compute_test_file_ratio(file_list)
        assert abs(ratio - 1 / 3) < 0.01
