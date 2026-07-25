"""Integration test: all 7 metrics extraction on a real repository.

Validates that M-01 through M-07 are all extractable from a git repo
with the correct observation structure and value ranges.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def multi_file_repo():
    """Create a git repo with mixed commit types for metric extraction."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "metric-test-repo"
        repo_path.mkdir()

        import subprocess

        subprocess.run(["git", "init", str(repo_path)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "dev@test.com"],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Developer"],
            capture_output=True,
            check=True,
        )

        # Create test files
        (repo_path / "test_core.py").write_text("def test_one(): pass\ndef test_two(): pass")
        (repo_path / "test_utils.py").write_text("def test_helper(): pass")

        # Create source files
        (repo_path / "core.py").write_text("x = 1")
        (repo_path / "utils.py").write_text("y = 2")

        # Make several commits with varied messages
        messages = [
            "feat: add new feature",
            "fix: resolve bug in core",
            "test: add unit tests",
            "refactor: clean up utils",
            "docs: update readme",
            "feat: implement parser",
            "fix: handle edge case",
            "test: add integration test",
            "chore: update dependencies",
            "feat: add validation",
        ]

        for i, msg in enumerate(messages):
            # Modify a file each commit
            (repo_path / f"core.py").write_text(f"x = {i}")
            subprocess.run(
                ["git", "-C", str(repo_path), "add", "."],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_path), "commit", "-m", msg],
                capture_output=True,
                check=True,
            )

        yield repo_path


class TestAllSevenMetrics:
    """Test that all 7 metrics are extractable from a real repo."""

    def test_m01_entropy_extraction(self, multi_file_repo):
        """M-01 (Specification Entropy) should produce a value in [0, 1]."""
        from miie.processing.extraction.engine import ExtractionEngine

        engine = ExtractionEngine()
        from miie.processing.ingestion import RepositoryIngestionEngine

        ingestion = RepositoryIngestionEngine()
        ctx = ingestion.ingest(str(multi_file_repo))

        collection, mdf = engine.extract(ctx, ["M-01"])
        assert "M-01" in mdf.metrics
        values = [v for ws in mdf.metrics["M-01"].values() for v in ws if v is not None]
        assert len(values) > 0
        assert all(0.0 <= v <= 1.0 for v in values)

    def test_m02_frequency_extraction(self, multi_file_repo):
        """M-02 (Commit Frequency) should produce count values >= 1."""
        from miie.processing.extraction.engine import ExtractionEngine

        engine = ExtractionEngine()
        from miie.processing.ingestion import RepositoryIngestionEngine

        ingestion = RepositoryIngestionEngine()
        ctx = ingestion.ingest(str(multi_file_repo))

        collection, mdf = engine.extract(ctx, ["M-02"])
        assert "M-02" in mdf.metrics
        values = [v for ws in mdf.metrics["M-02"].values() for v in ws if v is not None]
        assert len(values) > 0
        assert all(v >= 1.0 for v in values)

    def test_m03_churn_extraction(self, multi_file_repo):
        """M-03 (Code Churn) should produce non-negative ratio values."""
        from miie.processing.extraction.engine import ExtractionEngine

        engine = ExtractionEngine()
        from miie.processing.ingestion import RepositoryIngestionEngine

        ingestion = RepositoryIngestionEngine()
        ctx = ingestion.ingest(str(multi_file_repo))

        collection, mdf = engine.extract(ctx, ["M-03"])
        assert "M-03" in mdf.metrics
        values = [v for ws in mdf.metrics["M-03"].values() for v in ws if v is not None]
        assert len(values) > 0
        assert all(v >= 0.0 for v in values)

    def test_m04_coverage_extraction(self, multi_file_repo):
        """M-04 (Test Coverage) should produce a ratio in [0, 1]."""
        from miie.processing.extraction.engine import ExtractionEngine

        engine = ExtractionEngine()
        from miie.processing.ingestion import RepositoryIngestionEngine

        ingestion = RepositoryIngestionEngine()
        ctx = ingestion.ingest(str(multi_file_repo))

        collection, mdf = engine.extract(ctx, ["M-04"])
        assert "M-04" in mdf.metrics
        # M-04 is aggregate — single value in last window
        values = [v for ws in mdf.metrics["M-04"].values() for v in ws if v is not None]
        assert len(values) == 1
        assert 0.0 <= values[0] <= 1.0

    def test_m05_pr_latency_extraction(self, multi_file_repo):
        """M-05 (PR Review Latency) — without GitHub API, returns empty."""
        from miie.processing.extraction.engine import ExtractionEngine

        engine = ExtractionEngine()
        from miie.processing.ingestion import RepositoryIngestionEngine

        ingestion = RepositoryIngestionEngine()
        ctx = ingestion.ingest(str(multi_file_repo))

        # M-05 requires GitHub API — local repo has no remote
        collection, mdf = engine.extract(ctx, ["M-05"])
        assert "M-05" in mdf.metrics
        # Without GitHub token, values should be zeros (no API data)
        values = [v for ws in mdf.metrics["M-05"].values() for v in ws if v != 0.0]
        assert len(values) == 0  # No GitHub API access in test

    def test_m06_breadth_extraction(self, multi_file_repo):
        """M-06 (File Activity Breadth) should produce count values >= 1."""
        from miie.processing.extraction.engine import ExtractionEngine

        engine = ExtractionEngine()
        from miie.processing.ingestion import RepositoryIngestionEngine

        ingestion = RepositoryIngestionEngine()
        ctx = ingestion.ingest(str(multi_file_repo))

        collection, mdf = engine.extract(ctx, ["M-06"])
        assert "M-06" in mdf.metrics
        values = [v for ws in mdf.metrics["M-06"].values() for v in ws if v is not None]
        assert len(values) > 0
        assert all(v >= 1.0 for v in values)

    def test_m07_recency_extraction(self, multi_file_repo):
        """M-07 (Branch Activity Recency) should produce non-negative values."""
        from miie.processing.extraction.engine import ExtractionEngine

        engine = ExtractionEngine()
        from miie.processing.ingestion import RepositoryIngestionEngine

        ingestion = RepositoryIngestionEngine()
        ctx = ingestion.ingest(str(multi_file_repo))

        collection, mdf = engine.extract(ctx, ["M-07"])
        assert "M-07" in mdf.metrics
        values = [v for ws in mdf.metrics["M-07"].values() for v in ws if v is not None]
        assert len(values) > 0
        assert all(v >= 0.0 for v in values)

    def test_all_seven_together(self, multi_file_repo):
        """All 7 metrics should extract together without errors."""
        from miie.processing.extraction.engine import ExtractionEngine

        engine = ExtractionEngine()
        from miie.processing.ingestion import RepositoryIngestionEngine

        ingestion = RepositoryIngestionEngine()
        ctx = ingestion.ingest(str(multi_file_repo))

        all_metrics = ["M-01", "M-02", "M-03", "M-04", "M-05", "M-06", "M-07"]
        collection, mdf = engine.extract(ctx, all_metrics)

        for mid in all_metrics:
            assert mid in mdf.metrics, f"{mid} missing from MetricDataFrame"

    def test_cobertura_xml_parsing(self, tmp_path):
        """Cobertura XML parser should extract line-rate correctly."""
        from miie.providers.git import GitObservationProvider

        cobertura_xml = tmp_path / "coverage.xml"
        cobertura_xml.write_text(
            '<?xml version="1.0" ?>\n'
            '<coverage version="7.0" line-rate="0.85" '
            'branches-rate="0.72" complexity="5.0">\n'
            "</coverage>"
        )

        result = GitObservationProvider._parse_cobertura_xml(cobertura_xml)
        assert result == 0.85

    def test_cobertura_xml_missing(self, tmp_path):
        """Cobertura XML parser should return None for missing file."""
        from miie.providers.git import GitObservationProvider

        result = GitObservationProvider._parse_cobertura_xml(tmp_path / "nonexistent.xml")
        assert result is None

    def test_lcov_parsing(self, tmp_path):
        """lcov.info parser should extract LH/LF correctly."""
        from miie.providers.git import GitObservationProvider

        lcov = tmp_path / "lcov.info"
        lcov.write_text("TN:\nSF:/src/main.py\nLF:200\nLH:150\nend_of_record\n")

        result = GitObservationProvider._parse_lcov(lcov)
        assert result == pytest.approx(0.75)

    def test_dot_coverage_parsing(self, tmp_path):
        """.coverage JSON parser should extract coverage ratio correctly."""
        import json

        from miie.providers.git import GitObservationProvider

        dot_cov = tmp_path / ".coverage"
        dot_cov.write_text(
            json.dumps(
                {
                    "coverage": {
                        "main.py": [1, 1, 0, 1, 0],
                        "utils.py": [1, 1, 1, 1, 1],
                    }
                }
            )
        )

        result = GitObservationProvider._parse_dot_coverage(dot_cov)
        assert result == pytest.approx(8 / 10)
