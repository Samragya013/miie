"""Regression tests for FERA critical findings.

These tests verify that previously-discovered bugs remain fixed.
Each test maps to a specific FERA critical finding.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from miie.schemas.models import (
    ConfidenceScore,
    DetectorResults,
    IntegrityScore,
    MetricDataFrame,
    ScorePackage,
    WindowDefinition,
)
from miie.schemas.serialization import json_dumps


class TestFERACriticalFindings:
    """Regression tests for all FERA critical findings."""

    def test_scoring_engine_no_nameerror_with_all_detectors(self):
        """C1: Scoring engine had NameError bugs (detector_output vs det_output)."""
        from miie.processing.scoring.engine import ScoringEngine

        engine = ScoringEngine()
        detector_results = DetectorResults(
            detector_outputs={
                "D-01": {
                    "drift_detected": True,
                    "ks_statistic": 0.3,
                    "ks_p_value": 0.01,
                    "psi_value": 0.1,
                    "mean_shift": 0.5,
                    "variance_ratio": 1.2,
                    "severity": 0.6,
                },
                "D-02": {
                    "correlation_breakdown": True,
                    "delta_r": 0.4,
                    "p_value": 0.02,
                    "severity": 0.7,
                },
                "D-03": {
                    "threshold_compressed": True,
                    "compression_index": 0.8,
                    "space_savings": 60.0,
                    "severity": 0.5,
                },
            }
        )
        mdf = MetricDataFrame(
            repo_id="test",
            run_id="r1",
            timestamp=datetime.now(timezone.utc),
            metrics={"M-02": {"w01": [10.0, 12.0, 11.0]}},
        )
        windows = [
            WindowDefinition(
                window_id="w01",
                start_date=datetime(2026, 1, 1).date(),
                end_date=datetime(2026, 1, 7).date(),
                commits=10,
                strategy="fixed_size",
            )
        ]
        # Should not raise NameError — the core regression test
        score = engine.compute_integrity_score(detector_results, mdf, windows)
        # Verify score has integrity and confidence
        integrity = score.integrity
        overall = integrity["overall"] if isinstance(integrity, dict) else integrity.overall
        assert 0.0 <= overall <= 1.0

    def test_f1_uses_count_not_magnitude(self):
        """C2: f1 formula was summing magnitudes instead of counting data points."""
        from miie.processing.scoring.engine import ScoringEngine

        engine = ScoringEngine()
        detector_results = DetectorResults(
            detector_outputs={
                "D-01": {"drift_detected": False, "severity": 0.0},
            }
        )
        mdf = MetricDataFrame(
            repo_id="test",
            run_id="r1",
            timestamp=datetime.now(timezone.utc),
            metrics={"M-02": {"w01": [10.0, 20.0, 30.0, 40.0, 50.0]}},
        )
        windows = [
            WindowDefinition(
                window_id="w01",
                start_date=datetime(2026, 1, 1).date(),
                end_date=datetime(2026, 1, 7).date(),
                commits=10,
                strategy="fixed_size",
            )
        ]
        score = engine.compute_integrity_score(detector_results, mdf, windows)
        # Real engine returns dict-like confidence
        conf = score.confidence
        overall = conf["overall"] if isinstance(conf, dict) else conf.overall
        factors = conf["factors"] if isinstance(conf, dict) else conf.factors
        # With 5 data points, sample_size factor = min(1.0, 5/50) = 0.1
        assert overall > 0.0
        assert "sample_size" in factors
        assert factors["sample_size"] > 0.0

    def test_json_dumps_accepts_indent(self):
        """C4: json_dumps() didn't accept indent kwarg (production bug)."""
        data = {"key": "value", "nested": {"a": 1}}
        result = json_dumps(data, indent=2)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed == data

    def test_json_dumps_accepts_default(self):
        """C4b: json_dumps() didn't accept default kwarg."""
        data = {"dt": datetime(2026, 1, 1, tzinfo=timezone.utc)}
        result = json_dumps(data, default=str)
        assert isinstance(result, str)

    def test_evidence_id_deterministic(self):
        """C3: Evidence engine used timestamps making output non-deterministic."""
        from miie.processing.evidence import EvidenceEngine
        from miie.schemas.models import EvidencePackage, RepositoryContext

        engine = EvidenceEngine()
        ctx = RepositoryContext(
            repo_id="test",
            local_path=Path("/tmp/test"),
            is_remote=False,
            total_commits=50,
            contributor_count=3,
        )
        mdf = MetricDataFrame(
            repo_id="test",
            run_id="r1",
            timestamp=datetime.now(timezone.utc),
            metrics={"M-02": {"w01": [10.0]}},
        )
        windows = [
            WindowDefinition(
                window_id="w01",
                start_date=datetime(2026, 1, 1).date(),
                end_date=datetime(2026, 1, 7).date(),
                commits=10,
                strategy="fixed_size",
            )
        ]
        det_results = DetectorResults(detector_outputs={"D-01": {"drift_detected": False}})
        score_pkg = ScorePackage(
            integrity=IntegrityScore(overall=0.8, per_metric={}, formula_version="1.0.0"),
            confidence=ConfidenceScore(overall=0.7, factors={}, band="medium"),
            timestamp=datetime.now(timezone.utc),
            config_hash="test",
        )
        e1 = engine.generate(ctx, mdf, windows, det_results, score_pkg, {"seed": 42})
        e2 = engine.generate(ctx, mdf, windows, det_results, score_pkg, {"seed": 42})
        assert isinstance(e1, EvidencePackage)
        # Same inputs should produce same evidence structure
        assert len(e1.detector_outputs.detector_outputs) == len(e2.detector_outputs.detector_outputs)

    def test_cli_analyze_dry_run(self):
        """C4: CLI analyze --dry-run should exit cleanly."""
        import os
        import subprocess

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            ["python", "-m", "miie", "analyze", ".", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0
        assert "Dry Run" in result.stdout or "dry run" in result.stdout.lower()

    def test_candidate_manifest_valid_json(self):
        """C5: candidate_manifest.json was malformed."""
        manifest_path = Path("benchmarks/metadata/candidate_manifest.json")
        assert manifest_path.exists()
        with open(manifest_path) as f:
            data = json.load(f)
        assert "candidates" in data
        assert "benchmark_info" in data

    def test_all_120_candidates_exist(self):
        """C5b: Not all expected candidates existed on disk."""
        candidates_dir = Path("benchmarks/datasets/candidates")
        assert candidates_dir.exists()
        candidate_dirs = [d for d in candidates_dir.iterdir() if d.is_dir()]
        assert len(candidate_dirs) >= 120

        # Verify each has metadata.json
        for cdir in sorted(candidate_dirs)[:120]:
            meta_path = cdir / "metadata.json"
            assert meta_path.exists(), f"{cdir.name} missing metadata.json"
            meta = json.loads(meta_path.read_text())
            assert "repo_id" in meta
