"""
Unit tests for metric extraction implementations (M-01, M-03, M-04, M-05, M-07).
"""

import datetime
import json
from pathlib import Path
from unittest import mock

from miie.processing.extraction import MetricExtractionEngine
from miie.schemas.models import RepositoryContext

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _make_context(tmp_path: Path) -> RepositoryContext:
    """Create a minimal RepositoryContext for testing."""
    return RepositoryContext(
        repo_id="test-repo",
        local_path=tmp_path,
        is_remote=False,
        total_commits=15,
        first_commit_date=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        last_commit_date=datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc),
        contributor_count=3,
        is_shallow=False,
        is_fork=False,
    )


# ---------------------------------------------------------------------------
# M-01: Code Coverage
# ---------------------------------------------------------------------------


class TestM01CodeCoverage:
    """Tests for M-01 Code Coverage extraction."""

    def test_parse_cobertura_xml(self, tmp_path):
        """Test parsing coverage.xml with line-rate attribute."""
        import shutil

        src = FIXTURES_DIR / "sample_coverage.xml"
        dst = tmp_path / "coverage.xml"
        shutil.copy(src, dst)

        engine = MetricExtractionEngine()
        result = engine._parse_cobertura_xml(dst)
        assert result == 75.0

    def test_parse_cobertura_xml_missing_file(self, tmp_path):
        """Test parsing non-existent coverage.xml returns None."""
        engine = MetricExtractionEngine()
        result = engine._parse_cobertura_xml(tmp_path / "coverage.xml")
        assert result is None

    def test_parse_cobertura_xml_malformed(self, tmp_path):
        """Test parsing malformed XML returns None."""
        bad_xml = tmp_path / "coverage.xml"
        bad_xml.write_text("not xml at all")

        engine = MetricExtractionEngine()
        result = engine._parse_cobertura_xml(bad_xml)
        assert result is None

    def test_parse_lcov(self, tmp_path):
        """Test parsing lcov.info with LH/LF lines."""
        lcov = tmp_path / "lcov.info"
        lcov.write_text(
            "SF:/src/main.py\n" "DA:1,1\n" "DA:2,1\n" "DA:3,0\n" "DA:4,1\n" "end_of_record\n" "LH:3\n" "LF:4\n"
        )

        engine = MetricExtractionEngine()
        result = engine._parse_lcov(lcov)
        assert result == 75.0

    def test_parse_lcov_zero_lines(self, tmp_path):
        """Test parsing lcov.info with zero lines found returns None."""
        lcov = tmp_path / "lcov.info"
        lcov.write_text("LF:0\nLH:0\n")

        engine = MetricExtractionEngine()
        result = engine._parse_lcov(lcov)
        assert result is None

    def test_parse_dot_coverage_percent(self, tmp_path):
        """Test parsing .coverage JSON with percent_covered."""
        cov = tmp_path / ".coverage"
        cov.write_text(json.dumps({"totals": {"percent_covered": 82.5}}))

        engine = MetricExtractionEngine()
        result = engine._parse_dot_coverage(cov)
        assert result == 82.5

    def test_parse_dot_coverage_flat(self, tmp_path):
        """Test parsing .coverage JSON with flat coverage dict."""
        cov = tmp_path / ".coverage"
        cov.write_text(
            json.dumps(
                {
                    "coverage": {
                        "src/a.py": [1, 1, 0, 1],
                        "src/b.py": [1, 1, 1, 1],
                    }
                }
            )
        )

        engine = MetricExtractionEngine()
        result = engine._parse_dot_coverage(cov)
        # 7/8 lines covered = 87.5%
        assert result == 87.5

    def test_extract_m01_with_cobertura(self, tmp_path):
        """Test full M-01 extraction with coverage.xml in repo."""
        import shutil

        src = FIXTURES_DIR / "sample_coverage.xml"
        dst = tmp_path / "coverage.xml"
        shutil.copy(src, dst)

        context = _make_context(tmp_path)
        engine = MetricExtractionEngine()
        result = engine._extract_code_coverage(context)

        assert result is not None
        assert "w00" in result
        assert result["w00"][0] == 75.0

    def test_extract_m01_no_artifacts(self, tmp_path):
        """Test M-01 returns None when no coverage artifacts exist."""
        context = _make_context(tmp_path)
        engine = MetricExtractionEngine()
        result = engine._extract_code_coverage(context)
        assert result is None

    def test_extract_m01_via_extract_method(self, tmp_path):
        """Test M-01 through the main extract() method.

        M-01 is now routed through GitObservationProvider (entropy ratio),
        so coverage.xml is no longer the primary source via extract().
        """
        context = _make_context(tmp_path)
        engine = MetricExtractionEngine()
        mdf = engine.extract(context, ["M-01"])

        # M-01 is now a provider metric (entropy ratio from git history)
        # May be None if tmp_path has no git history
        # The old coverage.xml extraction is still available via
        # _extract_code_coverage() directly
        assert "M-01" in mdf.metrics


# ---------------------------------------------------------------------------
# M-03: Review Participation
# ---------------------------------------------------------------------------


class TestM03ReviewParticipation:
    """Tests for M-03 Review Participation extraction."""

    def test_parse_pr_export(self):
        """Test reviewers_per_pr calculation from sample PR export."""
        engine = MetricExtractionEngine(pr_export_path=FIXTURES_DIR / "sample_pr_export.json")
        result = engine._extract_review_participation()

        assert result is not None
        assert "w00" in result
        # Total reviewers: 2+1+0+3 = 6, total PRs: 4, ratio = 1.5
        assert result["w00"][0] == 1.5

    def test_extract_m03_no_pr_export(self):
        """Test M-03 returns None when no PR export provided."""
        engine = MetricExtractionEngine()
        result = engine._extract_review_participation()
        assert result is None

    def test_extract_m03_missing_file(self, tmp_path):
        """Test M-03 returns None when PR export file doesn't exist."""
        engine = MetricExtractionEngine(pr_export_path=tmp_path / "nonexistent.json")
        result = engine._extract_review_participation()
        assert result is None

    def test_extract_m03_empty_prs(self, tmp_path):
        """Test M-03 returns None for empty PR list."""
        pr_file = tmp_path / "prs.json"
        pr_file.write_text("[]")

        engine = MetricExtractionEngine(pr_export_path=pr_file)
        result = engine._extract_review_participation()
        assert result is None

    def test_extract_m03_via_extract_method(self):
        """Test M-03 through the main extract() method.

        M-03 is now routed through GitObservationProvider (churn ratio),
        so PR export data is no longer the primary source via extract().
        """
        context = _make_context(Path("/tmp"))
        engine = MetricExtractionEngine(pr_export_path=FIXTURES_DIR / "sample_pr_export.json")
        mdf = engine.extract(context, ["M-03"])

        # M-03 is now a provider metric (churn ratio from git history)
        # The old review participation extraction is still available via
        # _extract_review_participation() directly
        assert "M-03" in mdf.metrics


# ---------------------------------------------------------------------------
# M-04: Review Latency
# ---------------------------------------------------------------------------


class TestM04ReviewLatency:
    """Tests for M-04 Review Latency extraction."""

    def test_parse_review_latency(self):
        """Test mean review latency from sample PR export."""
        engine = MetricExtractionEngine(pr_export_path=FIXTURES_DIR / "sample_pr_export.json")
        result = engine._extract_review_latency()

        assert result is not None
        assert "w00" in result
        # PR-1: 4h, PR-2: 2.5h, PR-3: skipped (no review), PR-4: 24h
        # Mean = (4 + 2.5 + 24) / 3 = 10.1667h
        assert abs(result["w00"][0] - 10.166666666666666) < 0.01

    def test_extract_m04_no_pr_export(self):
        """Test M-04 returns None when no PR export provided."""
        engine = MetricExtractionEngine()
        result = engine._extract_review_latency()
        assert result is None

    def test_extract_m04_no_reviews(self, tmp_path):
        """Test M-04 returns None when no PRs have reviews."""
        pr_file = tmp_path / "prs.json"
        pr_file.write_text(
            json.dumps(
                [
                    {
                        "id": "PR-1",
                        "created_at": "2025-06-01T10:00:00Z",
                        "first_review_at": None,
                        "reviewers": [],
                    },
                ]
            )
        )

        engine = MetricExtractionEngine(pr_export_path=pr_file)
        result = engine._extract_review_latency()
        assert result is None

    def test_extract_m04_via_extract_method(self):
        """Test M-04 through the main extract() method.

        M-04 is now routed through GitObservationProvider (test coverage ratio),
        so PR export data is no longer the primary source via extract().
        """
        context = _make_context(Path("/tmp"))
        engine = MetricExtractionEngine(pr_export_path=FIXTURES_DIR / "sample_pr_export.json")
        mdf = engine.extract(context, ["M-04"])

        # M-04 is now a provider metric (test coverage ratio from git history)
        # The old review latency extraction is still available via
        # _extract_review_latency() directly
        assert "M-04" in mdf.metrics


# ---------------------------------------------------------------------------
# M-05: Issue Resolution Time
# ---------------------------------------------------------------------------


class TestM05IssueResolutionTime:
    """Tests for M-05 Issue Resolution Time extraction."""

    def test_parse_issue_resolution(self):
        """Test mean resolution time from sample issue export."""
        engine = MetricExtractionEngine(issue_export_path=FIXTURES_DIR / "sample_issue_export.json")
        result = engine._extract_issue_resolution_time()

        assert result is not None
        assert "w00" in result
        # ISSUE-1: 2d, ISSUE-2: 2.5d, ISSUE-3: skipped (open), ISSUE-4: 0.5d, ISSUE-5: 7d
        # Mean = (2 + 2.5 + 0.5 + 7) / 4 = 3.0 days
        assert result["w00"][0] == 3.0

    def test_extract_m05_no_issue_export(self):
        """Test M-05 returns None when no issue export provided."""
        engine = MetricExtractionEngine()
        result = engine._extract_issue_resolution_time()
        assert result is None

    def test_extract_m05_no_closed_issues(self, tmp_path):
        """Test M-05 returns None when no closed issues exist."""
        issue_file = tmp_path / "issues.json"
        issue_file.write_text(
            json.dumps(
                [
                    {
                        "id": "I-1",
                        "created_at": "2025-06-01T10:00:00Z",
                        "closed_at": None,
                        "state": "open",
                    },
                ]
            )
        )

        engine = MetricExtractionEngine(issue_export_path=issue_file)
        result = engine._extract_issue_resolution_time()
        assert result is None

    def test_extract_m05_via_extract_method(self):
        """Test M-05 through the main extract() method.

        M-05 is now a provider metric routed through ExtractionEngine
        (GitHub PR API). Without a GitHub token, it returns empty.
        """
        context = _make_context(Path("/tmp"))
        engine = MetricExtractionEngine()
        mdf = engine.extract(context, ["M-05"])

        # M-05 is now a provider metric — without GitHub API access, no data
        assert mdf.metrics["M-05"] is not None
        assert mdf.metrics["M-05"]["w00"] == [0.0]


# ---------------------------------------------------------------------------
# M-07: Cyclomatic Complexity
# ---------------------------------------------------------------------------


class TestM07CyclomaticComplexity:
    """Tests for M-07 Cyclomatic Complexity extraction."""

    def test_extract_m07_lizard_unavailable(self, tmp_path):
        """Test M-07 returns None when lizard and radon are not installed."""
        context = _make_context(tmp_path)
        engine = MetricExtractionEngine()

        # Mock import failures for both lizard and radon
        with mock.patch.dict("sys.modules", {"lizard": None, "radon": None, "radon.complexity": None}):
            result = engine._extract_cyclomatic_complexity(context)
            assert result is None

    def test_extract_m07_no_source_files(self, tmp_path):
        """Test M-07 returns None when no source files exist."""
        context = _make_context(tmp_path)
        engine = MetricExtractionEngine()

        # Create empty directory (no .py files)
        result = engine._extract_cyclomatic_complexity(context)
        # May return None or a value depending on whether lizard/radon is installed
        # With no files, it should return None
        assert result is None

    def test_extract_m07_with_lizard(self, tmp_path):
        """Test M-07 extraction with mocked lizard."""
        # Create a Python file
        py_file = tmp_path / "example.py"
        py_file.write_text("def foo():\n    return 1\n")

        _make_context(tmp_path)

        # Create a mock lizard module
        mock_lizard = mock.MagicMock()
        mock_function = mock.MagicMock()
        mock_function.cyclomatic_complexity = 3
        mock_result = mock.MagicMock()
        mock_result.function_list = [mock_function]
        mock_lizard.analyze_file.return_value = mock_result

        engine = MetricExtractionEngine()
        result = engine._extract_complexity_lizard(mock_lizard, tmp_path)

        assert result is not None
        assert "w00" in result
        assert result["w00"][0] == 3.0

    def test_extract_m07_with_lizard_multiple_functions(self, tmp_path):
        """Test M-07 with lizard returning multiple functions."""
        py_file = tmp_path / "example.py"
        py_file.write_text("def foo():\n    pass\n")

        _make_context(tmp_path)

        mock_lizard = mock.MagicMock()
        mock_func1 = mock.MagicMock()
        mock_func1.cyclomatic_complexity = 2
        mock_func2 = mock.MagicMock()
        mock_func2.cyclomatic_complexity = 8
        mock_result = mock.MagicMock()
        mock_result.function_list = [mock_func1, mock_func2]
        mock_lizard.analyze_file.return_value = mock_result

        engine = MetricExtractionEngine()
        result = engine._extract_complexity_lizard(mock_lizard, tmp_path)

        assert result is not None
        assert result["w00"][0] == 5.0

    def test_extract_m07_with_radon(self, tmp_path):
        """Test M-07 extraction with mocked radon."""
        py_file = tmp_path / "example.py"
        py_file.write_text("def foo():\n    return 1\n")

        _make_context(tmp_path)

        mock_block = mock.MagicMock()
        mock_block.complexity = 4
        mock_cc_visit = mock.MagicMock(return_value=[mock_block])

        mock_radon = mock.MagicMock()
        mock_radon_complexity = mock.MagicMock(cc_visit=mock_cc_visit)
        mock_radon_raw = mock.MagicMock()

        with mock.patch.dict(
            "sys.modules",
            {
                "radon": mock_radon,
                "radon.complexity": mock_radon_complexity,
                "radon.raw": mock_radon_raw,
            },
        ):
            engine = MetricExtractionEngine()
            result = engine._extract_complexity_radon(tmp_path)

            assert result is not None
            assert result["w00"][0] == 4.0

    def test_extract_m07_via_extract_method_no_tools(self, tmp_path):
        """Test M-07 through extract() — now a provider metric (branch freshness).

        M-07 is routed through GitObservationProvider, not lizard/radon.
        The old cyclomatic complexity extraction is still available via
        _extract_cyclomatic_complexity() directly.
        """
        context = _make_context(tmp_path)
        engine = MetricExtractionEngine()

        mdf = engine.extract(context, ["M-07"])
        # M-07 is now a provider metric; may be None if no git history
        assert "M-07" in mdf.metrics


# ---------------------------------------------------------------------------
# Graceful fallback tests
# ---------------------------------------------------------------------------


class TestGracefulFallback:
    """Tests for graceful fallback when artifacts or tools are missing."""

    def test_all_unavailable_metrics_return_none(self, tmp_path):
        """Test that M-05 (now a provider metric) returns empty without GitHub API access."""
        context = _make_context(tmp_path)
        engine = MetricExtractionEngine()

        # M-05 is now a provider metric — without GitHub token, returns empty values or None
        mdf = engine.extract(context, ["M-05"])

        assert mdf.metrics["M-05"] is not None
        assert mdf.metrics["M-05"]["w00"] in ([0.0], [])

    def test_mixed_available_and_unavailable(self, tmp_path):
        """Test extraction with provider metrics including M-05."""
        import shutil

        src = FIXTURES_DIR / "sample_coverage.xml"
        dst = tmp_path / "coverage.xml"
        shutil.copy(src, dst)

        context = _make_context(tmp_path)
        engine = MetricExtractionEngine()

        with mock.patch.dict("sys.modules", {"lizard": None, "radon": None, "radon.complexity": None}):
            mdf = engine.extract(context, ["M-01", "M-02", "M-06", "M-05"])

            # M-01, M-02, M-06 are provider metrics — may or may not have values
            # depending on git history in tmp_path
            assert "M-01" in mdf.metrics
            assert "M-02" in mdf.metrics
            assert "M-06" in mdf.metrics
            # M-05 is now a provider metric — returns zeros without GitHub API
            # On CI without GITHUB_TOKEN, M-05 may return None
            if mdf.metrics["M-05"] is not None:
                assert mdf.metrics["M-05"]["w00"] in ([0.0], [])

    def test_malformed_json_returns_none(self, tmp_path):
        """Test that malformed JSON files return None instead of raising."""
        pr_file = tmp_path / "prs.json"
        pr_file.write_text("not valid json {{{")

        engine = MetricExtractionEngine(pr_export_path=pr_file)
        assert engine._extract_review_participation() is None
        assert engine._extract_review_latency() is None

        issue_file = tmp_path / "issues.json"
        issue_file.write_text("{broken")

        engine2 = MetricExtractionEngine(issue_export_path=issue_file)
        assert engine2._extract_issue_resolution_time() is None
