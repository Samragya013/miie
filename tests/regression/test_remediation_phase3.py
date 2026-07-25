"""Regression tests for remediation Phase 3 fixes.

Verifies that the following fixes remain working:
- Issue 23: CLI help text improvements
- Issue 24: Optional dependency groups in pyproject.toml
- Issue 32: CORS configuration
"""

import pytest

# ---------------------------------------------------------------------------
# CLI Help Text (Issue 23)
# ---------------------------------------------------------------------------


class TestCLIHelpText:
    """Issue 23: Improved help text for CLI commands."""

    def test_analyze_help_has_examples(self):
        """analyze --help should show usage examples."""
        from click.testing import CliRunner

        from miie.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "example" in result.output.lower()

    def test_ingest_help_has_examples(self):
        """ingest --help should show usage examples."""
        from click.testing import CliRunner

        from miie.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "example" in result.output.lower()

    def test_detect_help_lists_detectors(self):
        """detect --help should list available detectors."""
        from click.testing import CliRunner

        from miie.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["detect", "--help"])
        assert result.exit_code == 0
        assert "D-01" in result.output
        assert "D-02" in result.output
        assert "D-03" in result.output

    def test_export_help_lists_formats(self):
        """export --help should list supported formats."""
        from click.testing import CliRunner

        from miie.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["export", "--help"])
        assert result.exit_code == 0
        assert "json" in result.output.lower()
        assert "csv" in result.output.lower()

    def test_status_help_has_examples(self):
        """status --help should show usage examples."""
        from click.testing import CliRunner

        from miie.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0
        assert "example" in result.output.lower()


# ---------------------------------------------------------------------------
# Optional Dependencies (Issue 24)
# ---------------------------------------------------------------------------


class TestOptionalDependencies:
    """Issue 24: Optional dependency groups in pyproject.toml."""

    def test_pyproject_has_extras(self):
        """pyproject.toml should define optional dependency groups."""
        import tomllib
        from pathlib import Path

        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

        extras = data.get("tool", {}).get("poetry", {}).get("extras", {})
        assert "excel" in extras, "Missing 'excel' extras group"
        assert "all" in extras, "Missing 'all' extras group"

    def test_extras_include_pandas(self):
        """excel extras should include pandas."""
        import tomllib
        from pathlib import Path

        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

        excel_deps = data["tool"]["poetry"]["extras"]["excel"]
        assert "pandas" in excel_deps


# ---------------------------------------------------------------------------
# CORS Configuration (Issue 32)
# ---------------------------------------------------------------------------


class TestCORSConfiguration:
    """Issue 32: CORS restricted to localhost."""

    def test_cors_middleware_configured(self):
        """App should have CORS middleware."""
        from miie.api.server import app

        middleware_classes = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in middleware_classes
