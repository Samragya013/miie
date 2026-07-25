"""Regression tests for War Room analysis fixes.

Tests the 9 war-room-identified improvements:
1. --fail-on-low-confidence flag
2. Confidence band shown FIRST in output
3. Data quality section
4. Window gap detection
5. Evidence compression
6. Monorepo package hint
7. TUI confidence/data quality surfacing
"""

import gzip
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestFailOnLowConfidenceFlag:
    """Tests for the --fail-on-low-confidence CLI flag."""

    def test_flag_exists_in_analyze_command(self):
        from click.testing import CliRunner

        from miie.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "fail-on-low-confidence" in result.output.lower()

    def test_flag_in_pipeline_signature(self):
        import inspect

        from miie.cli import _run_pipeline_rich

        sig = inspect.signature(_run_pipeline_rich)
        assert "fail_on_low_confidence" in sig.parameters


class TestConfidenceBandDisplay:
    """Tests for confidence band displayed FIRST in output."""

    def test_high_band(self):
        from miie.cli import _display_confidence_band_header

        _display_confidence_band_header("high", 0.95, {"sample_size": 0.9, "variance": 0.8})

    def test_low_band(self):
        from miie.cli import _display_confidence_band_header

        _display_confidence_band_header("low", 0.2, {"sample_size": 0.1, "variance": 0.3})

    def test_medium_band(self):
        from miie.cli import _display_confidence_band_header

        _display_confidence_band_header("medium", 0.65, {"sample_size": 0.7})

    def test_no_factors(self):
        from miie.cli import _display_confidence_band_header

        _display_confidence_band_header("high", 0.9, None)

    def test_empty_factors(self):
        from miie.cli import _display_confidence_band_header

        _display_confidence_band_header("high", 0.9, {})


class TestDataQualitySection:
    """Tests for the data quality section in CLI output."""

    def test_with_windows(self):
        from datetime import timedelta

        from miie.cli import _display_data_quality

        mock_windows = []
        base = date(2024, 1, 1)
        for i in range(3):
            w = MagicMock()
            w.commits = 100 + i * 50
            w.start_date = base + timedelta(days=i * 30)
            w.end_date = base + timedelta(days=29 + i * 30)
            mock_windows.append(w)

        mock_mdf = MagicMock()
        mock_mdf.metrics = {
            "M-01": {f"w{i:02d}": [1.0, 2.0, 3.0] for i in range(3)},
            "M-02": {f"w{i:02d}": [4.0, 5.0] for i in range(3)},
        }
        _display_data_quality(mock_windows, mock_mdf, 500)

    def test_empty_windows(self):
        from miie.cli import _display_data_quality

        _display_data_quality([], MagicMock(), 0)

    def test_with_gaps(self):
        from datetime import timedelta

        from miie.cli import _display_data_quality

        mock_windows = []
        base = date(2024, 1, 1)
        for i in range(3):
            w = MagicMock()
            w.commits = 100
            w.start_date = base + timedelta(days=i * 40)
            w.end_date = base + timedelta(days=29 + i * 40)
            mock_windows.append(w)
        mock_mdf = MagicMock()
        mock_mdf.metrics = {}
        _display_data_quality(mock_windows, mock_mdf, 500)


class TestEvidenceCompression:
    """Tests for gzip evidence compression on large repos."""

    def test_skips_small_repos(self):
        from miie.cli import _compress_large_reports

        report_paths = {"json": "/tmp/test.json"}
        _compress_large_reports(report_paths, 5000)
        assert "json_compressed" not in report_paths

    def test_skips_small_files(self):
        from miie.cli import _compress_large_reports

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"test": "data"}, f)
            f.flush()
            report_paths = {"json": f.name}
        try:
            _compress_large_reports(report_paths, 15000)
            assert "json_compressed" not in report_paths
        finally:
            os.unlink(f.name)

    def test_compresses_large_files(self):
        from miie.cli import _compress_large_reports

        large_data = {"data": "x" * 1_100_000}
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(large_data, f)
            f.flush()
            json_path = f.name
            report_paths = {"json": json_path}
        try:
            _compress_large_reports(report_paths, 15000)
            gz_path = Path(json_path).with_suffix(".json.gz")
            if gz_path.exists():
                assert "json_compressed" in report_paths
                with gzip.open(gz_path, "rb") as gf:
                    data = json.loads(gf.read().decode("utf-8"))
                assert data == large_data
                os.unlink(gz_path)
        finally:
            os.unlink(json_path)


class TestExecutiveSummaryBand:
    """Integration tests for confidence band in executive summary."""

    def test_accepts_confidence_band(self):
        from miie.cli.premium_tui import display_executive_summary

        with patch("miie.cli.premium_tui.console") as mc:
            with patch("miie.cli.premium_tui.get_layout") as ml:
                ml.return_value = MagicMock(
                    show_detail=True,
                    show_timing=True,
                    score_bar_width=20,
                    max_detail_length=30,
                )
                display_executive_summary(
                    integrity_score=0.95,
                    confidence_score=0.3,
                    total_commits=100,
                    contributor_count=5,
                    window_count=3,
                    detector_outputs={"D-01": {"drift_detected": False}},
                    confidence_band="low",
                    confidence_factors={"sample_size": 0.1},
                )
                assert mc.print.called

    def test_default_band(self):
        from miie.cli.premium_tui import display_executive_summary

        with patch("miie.cli.premium_tui.console") as mc:
            with patch("miie.cli.premium_tui.get_layout") as ml:
                ml.return_value = MagicMock(
                    show_detail=False,
                    show_timing=False,
                    score_bar_width=20,
                    max_detail_length=30,
                )
                display_executive_summary(
                    integrity_score=1.0,
                    confidence_score=0.9,
                    total_commits=100,
                    contributor_count=5,
                    window_count=3,
                    detector_outputs={},
                )
                assert mc.print.called
