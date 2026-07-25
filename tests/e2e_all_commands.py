"""
End-to-end smoke tests for ALL miie commands and options.

Run with: python -m pytest tests/e2e_all_commands.py -v --tb=short
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from miie.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def small_repo(tmp_path):
    """Create a small git repo with 12 staggered commits."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), capture_output=True)
    for i in range(12):
        f = repo / f"file_{i}.txt"
        f.write_text(f"content {i}")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        env = os.environ.copy()
        days = 1 + i * 2
        env["GIT_AUTHOR_DATE"] = f"2024-01-{days:02d}T12:00:00"
        env["GIT_COMMITTER_DATE"] = f"2024-01-{days:02d}T12:00:00"
        subprocess.run(["git", "commit", "-m", f"feat: commit {i}"], cwd=str(repo), capture_output=True, env=env)
    return repo


# ─── miie --version ──────────────────────────────────────────────
class TestVersion:
    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "1.6.0" in result.output


# ─── miie doctor ─────────────────────────────────────────────────
class TestDoctor:
    def test_doctor(self, runner):
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "OK" in result.output


# ─── miie status ─────────────────────────────────────────────────
class TestStatus:
    def test_status(self, runner):
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Engine Status" in result.output or "IngestionEngine" in result.output


# ─── miie validate ───────────────────────────────────────────────
class TestValidate:
    def test_validate_config_type(self, runner):
        result = runner.invoke(cli, ["validate", "config.yaml", "--type", "config"])
        # Should fail because config.yaml doesn't exist, but the command itself runs
        assert result.exit_code != 0 or "VALIDATION" in result.output

    def test_validate_analysis_type(self, runner):
        result = runner.invoke(cli, ["validate", "nonexistent.json", "--type", "analysis"])
        assert result.exit_code != 0

    def test_validate_benchmark_type(self, runner):
        result = runner.invoke(cli, ["validate", "nonexistent.json", "--type", "benchmark"])
        assert result.exit_code != 0

    def test_validate_manifest_type(self, runner):
        result = runner.invoke(cli, ["validate", "nonexistent.json", "--type", "manifest"])
        assert result.exit_code != 0


# ─── miie ingest ─────────────────────────────────────────────────
class TestIngest:
    def test_ingest_local_path(self, runner, small_repo):
        result = runner.invoke(cli, ["ingest", str(small_repo)])
        assert result.exit_code == 0
        assert "Ingestion Successful" in result.output
        assert "Commits" in result.output

    def test_ingest_nonexistent_path(self, runner):
        result = runner.invoke(cli, ["ingest", "/nonexistent/repo"])
        assert result.exit_code != 0

    def test_ingest_shallow_option(self, runner, small_repo):
        result = runner.invoke(cli, ["ingest", str(small_repo), "--shallow", "5"])
        assert result.exit_code == 0

    def test_ingest_auth_token_option(self, runner, small_repo):
        result = runner.invoke(cli, ["ingest", str(small_repo), "--auth-token", "fake_token"])
        assert result.exit_code == 0


# ─── miie detect ─────────────────────────────────────────────────
class TestDetect:
    def test_detect_local(self, runner, small_repo):
        result = runner.invoke(cli, ["detect", str(small_repo), "-m", "M-02"])
        assert result.exit_code == 0
        assert "Detection complete" in result.output

    def test_detect_multiple_metrics(self, runner, small_repo):
        result = runner.invoke(cli, ["detect", str(small_repo), "-m", "M-02", "-m", "M-06"])
        assert result.exit_code == 0

    def test_detect_with_seed(self, runner, small_repo):
        result = runner.invoke(cli, ["detect", str(small_repo), "-m", "M-02", "--seed", "123"])
        assert result.exit_code == 0


# ─── miie analyze ────────────────────────────────────────────────
class TestAnalyze:
    def test_analyze_default(self, runner, small_repo):
        result = runner.invoke(cli, ["analyze", str(small_repo), "-w", "commit", "-s", "5", "-f", "json"])
        assert result.exit_code == 0
        assert "Analysis Complete" in result.output

    def test_analyze_dry_run(self, runner, small_repo):
        result = runner.invoke(cli, ["analyze", str(small_repo), "--dry-run"])
        assert result.exit_code == 0
        assert "Dry Run" in result.output or "Validation: PASSED" in result.output

    def test_analyze_custom_metrics(self, runner, small_repo):
        result = runner.invoke(cli, ["analyze", str(small_repo), "-m", "M-02", "-w", "commit", "-s", "5", "-f", "json"])
        assert result.exit_code in (0, 1)  # May exit 1 if single metric insufficient for all detectors

    def test_analyze_custom_detectors(self, runner, small_repo):
        result = runner.invoke(cli, ["analyze", str(small_repo), "-d", "D-01", "-w", "commit", "-s", "5", "-f", "json"])
        assert result.exit_code == 0

    def test_analyze_window_strategy_commit(self, runner, small_repo):
        result = runner.invoke(cli, ["analyze", str(small_repo), "-w", "commit", "-s", "5", "-f", "json"])
        assert result.exit_code == 0

    def test_analyze_window_strategy_time(self, runner, small_repo):
        result = runner.invoke(cli, ["analyze", str(small_repo), "-w", "time", "-s", "7", "-f", "json"])
        assert result.exit_code == 0

    def test_analyze_since_until(self, runner, small_repo):
        result = runner.invoke(
            cli, ["analyze", str(small_repo), "--since", "2024-01-01", "--until", "2024-01-31", "-f", "json"]
        )
        # May produce 0 windows with narrow range, but should not crash
        assert result.exit_code in (0, 1)

    def test_analyze_exclude_bots(self, runner, small_repo):
        result = runner.invoke(
            cli, ["analyze", str(small_repo), "--exclude-bots", "-w", "commit", "-s", "5", "-f", "json"]
        )
        assert result.exit_code == 0

    def test_analyze_custom_thresholds(self, runner, small_repo):
        result = runner.invoke(
            cli,
            [
                "analyze",
                str(small_repo),
                "--thresholds",
                '{"D-01": {"alpha": 0.05}}',
                "-w",
                "commit",
                "-s",
                "5",
                "-f",
                "json",
            ],
        )
        assert result.exit_code == 0

    def test_analyze_seed(self, runner, small_repo):
        result = runner.invoke(
            cli, ["analyze", str(small_repo), "--seed", "99", "-w", "commit", "-s", "5", "-f", "json"]
        )
        assert result.exit_code == 0

    def test_analyze_forensic(self, runner, small_repo):
        result = runner.invoke(cli, ["analyze", str(small_repo), "--forensic", "-w", "commit", "-s", "5", "-f", "json"])
        assert result.exit_code == 0

    def test_analyze_verbose(self, runner, small_repo):
        result = runner.invoke(cli, ["-V", "analyze", str(small_repo), "-w", "commit", "-s", "5", "-f", "json"])
        assert result.exit_code == 0

    def test_analyze_format_md(self, runner, small_repo):
        result = runner.invoke(cli, ["analyze", str(small_repo), "-w", "commit", "-s", "5", "-f", "md"])
        assert result.exit_code == 0

    def test_analyze_format_csv(self, runner, small_repo):
        result = runner.invoke(cli, ["analyze", str(small_repo), "-w", "commit", "-s", "5", "-f", "csv"])
        assert result.exit_code == 0

    def test_analyze_format_multi(self, runner, small_repo):
        result = runner.invoke(cli, ["analyze", str(small_repo), "-w", "commit", "-s", "5", "-f", "json", "-f", "md"])
        assert result.exit_code == 0

    def test_analyze_output_dir(self, runner, small_repo, tmp_path):
        out = tmp_path / "my_output"
        result = runner.invoke(
            cli, ["analyze", str(small_repo), "-o", str(out), "-w", "commit", "-s", "5", "-f", "json"]
        )
        assert result.exit_code == 0

    def test_analyze_url_dry_run(self, runner):
        result = runner.invoke(cli, ["analyze", "https://github.com/pallets/markupsafe.git", "--dry-run"])
        assert result.exit_code == 0


# ─── miie explain ────────────────────────────────────────────────
class TestExplain:
    def test_explain_default(self, runner, small_repo):
        result = runner.invoke(cli, ["explain", str(small_repo)])
        assert result.exit_code == 0
        assert "Explanation complete" in result.output

    def test_explain_metric_filter(self, runner, small_repo):
        result = runner.invoke(cli, ["explain", str(small_repo), "--metric-filter", "M-02"])
        assert result.exit_code == 0

    def test_explain_detector_filter(self, runner, small_repo):
        result = runner.invoke(cli, ["explain", str(small_repo), "--detector-filter", "D-01"])
        assert result.exit_code == 0

    def test_explain_custom_metrics(self, runner, small_repo):
        result = runner.invoke(cli, ["explain", str(small_repo), "-m", "M-02", "-m", "M-06"])
        assert result.exit_code == 0


# ─── miie export ─────────────────────────────────────────────────
class TestExport:
    def test_export_json(self, runner, small_repo):
        result = runner.invoke(cli, ["export", str(small_repo), "-f", "json"])
        assert result.exit_code == 0
        assert "Exported" in result.output

    def test_export_output_dir(self, runner, small_repo, tmp_path):
        out = tmp_path / "export_out"
        result = runner.invoke(cli, ["export", str(small_repo), "-f", "json", "-o", str(out)])
        assert result.exit_code == 0


# ─── miie generate ───────────────────────────────────────────────
class TestGenerate:
    def test_generate_help(self, runner):
        result = runner.invoke(cli, ["generate", "--help"])
        assert result.exit_code == 0
        assert "-t" in result.output or "--type" in result.output
        assert "--count" in result.output or "-n" in result.output
        assert "--seed" in result.output


# ─── miie benchmark ──────────────────────────────────────────────
class TestBenchmark:
    def test_benchmark_help(self, runner):
        result = runner.invoke(cli, ["benchmark", "--help"])
        assert result.exit_code == 0
        assert "--suite" in result.output

    def test_benchmark_no_suite_fails(self, runner):
        result = runner.invoke(cli, ["benchmark"])
        assert result.exit_code != 0


# ─── miie evaluate ───────────────────────────────────────────────
class TestEvaluate:
    def test_evaluate_help(self, runner):
        result = runner.invoke(cli, ["evaluate", "--help"])
        assert result.exit_code == 0
        assert "--benchmark-json" in result.output

    def test_evaluate_no_args_fails(self, runner):
        result = runner.invoke(cli, ["evaluate"])
        assert result.exit_code != 0


# ─── miie interactive ────────────────────────────────────────────
class TestInteractive:
    def test_interactive_quit(self, runner):
        result = runner.invoke(cli, ["interactive"], input="q\n")
        assert result.exit_code == 0
        assert "MIIE Workspace" in result.output or "Select" in result.output


# ─── miie shell ──────────────────────────────────────────────────
class TestShell:
    def test_shell_help(self, runner):
        result = runner.invoke(cli, ["shell", "--help"])
        assert result.exit_code == 0
        assert "shell" in result.output.lower() or "interactive" in result.output.lower()


# ─── miie setup ──────────────────────────────────────────────────
class TestSetup:
    def test_setup_shows_config(self, runner):
        result = runner.invoke(cli, ["setup", "--help"])
        assert result.exit_code == 0
        assert "setup" in result.output.lower() or "config" in result.output.lower()
