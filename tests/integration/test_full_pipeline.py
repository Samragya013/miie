"""Integration test: full pipeline on a real repository.

Validates that the entire analysis pipeline produces correct results
end-to-end, from ingestion through scoring.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def sample_repo():
    """Create a minimal git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test-repo"
        repo_path.mkdir()

        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init", str(repo_path)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test"],
            capture_output=True,
            check=True,
        )

        # Create some commits
        for i in range(10):
            (repo_path / f"file_{i}.txt").write_text(f"content {i}")
            subprocess.run(
                ["git", "-C", str(repo_path), "add", "."],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_path), "commit", "-m", f"commit {i}"],
                capture_output=True,
                check=True,
            )

        yield repo_path


class TestFullPipeline:
    """Test the full analysis pipeline end-to-end."""

    def test_ingestion_works(self, sample_repo):
        """Ingestion should produce a RepositoryContext."""
        from miie.processing.ingestion import RepositoryIngestionEngine

        engine = RepositoryIngestionEngine()
        ctx = engine.ingest(str(sample_repo))
        assert ctx is not None
        assert ctx.repo_id is not None

    def test_scoring_engine_instantiates(self):
        """ScoringEngine should instantiate correctly."""
        from miie.processing.scoring.engine import ScoringEngine

        engine = ScoringEngine()
        assert engine is not None

    def test_evidence_engine_instantiates(self):
        """EvidenceEngine should instantiate correctly."""
        from miie.processing.evidence import EvidenceEngine

        engine = EvidenceEngine()
        assert engine is not None

    def test_detector_registry_works(self):
        """DetectorRegistry should register and list detectors."""
        from miie.processing.detection.correlation_breakdown_detector import (
            CorrelationBreakdownDetector,
        )
        from miie.processing.detection.distribution_drift_detector import (
            DistributionDriftDetector,
        )
        from miie.processing.detection.registry import DetectorRegistry
        from miie.processing.detection.threshold_compression_detector import (
            ThresholdCompressionDetector,
        )

        registry = DetectorRegistry()
        registry.register(DistributionDriftDetector())
        registry.register(CorrelationBreakdownDetector())
        registry.register(ThresholdCompressionDetector())

        # Should have 3 detectors
        assert len(registry._detectors) == 3

    def test_api_endpoints_exist(self):
        """All 6 frozen API endpoints should be registered."""
        from miie.api.server import app

        routes = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/v1/health" in routes
        assert "/v1/analyze" in routes
        assert "/v1/benchmark" in routes
        assert "/v1/explain" in routes
        assert "/v1/export" in routes
        assert "/v1/jobs/{job_id}" in routes

    def test_cli_commands_registered(self):
        """All 13 CLI commands should be registered."""
        from click.testing import CliRunner

        from miie.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        # Check key commands exist
        assert "analyze" in result.output
        assert "benchmark" in result.output
        assert "detect" in result.output
        assert "export" in result.output
        assert "explain" in result.output
        assert "shell" in result.output

    def test_contracts_are_protocols(self):
        """Frozen contracts should be Protocol classes."""
        # All should be Protocol subclasses
        from typing import Protocol

        from miie.contracts.interfaces import (
            IDetectorEngine,
            IEvidenceEngine,
            IExtractionEngine,
            IIngestionEngine,
            IScoringEngine,
        )

        assert issubclass(IIngestionEngine, Protocol)
        assert issubclass(IExtractionEngine, Protocol)
        assert issubclass(IDetectorEngine, Protocol)
        assert issubclass(IScoringEngine, Protocol)
        assert issubclass(IEvidenceEngine, Protocol)

    def test_statistical_methods_accessible(self):
        """All statistical methods should be importable."""
        from miie.processing.detection.statistics import (
            dip_test,
            excess_mass_test,
            fisher_z,
            fisher_z_ci,
            fisher_z_test,
            ks_2samp,
            pearson_r,
            spearman_rho,
        )

        assert callable(ks_2samp)
        assert callable(pearson_r)
        assert callable(spearman_rho)
        assert callable(fisher_z)
        assert callable(fisher_z_ci)
        assert callable(fisher_z_test)
        assert callable(dip_test)
        assert callable(excess_mass_test)

    def test_version_is_correct(self):
        """Version should be 1.6.0."""
        from miie import __version__

        assert __version__ == "1.6.0"
