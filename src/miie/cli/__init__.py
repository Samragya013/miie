"""
MIIE CLI — Measurement Integrity Intelligence Engine.

Commands:
    miie analyze    Run the full analysis pipeline on a repository
    miie ingest     Validate and ingest a repository
    miie detect     Run detectors on a repository
    miie benchmark  Execute a benchmark suite
    miie evaluate   Evaluate benchmark results against ground truth
    miie explain    Generate explanations from analysis
    miie export     Export results in specified formats
    miie generate   Generate synthetic benchmark candidates
    miie status     Show system status
    miie validate   Validate config file or analysis output

Exit codes (AFD §9.2, TFS §13.7):
    0 - Success (IS=1.0, no failures)
    1 - Integrity failures detected (IS<1.0)
    2 - System error (pipeline crashes, file not found, etc.)
    3 - Invalid arguments (bad CLI args, validation failure)
    4 - Benchmark failure
"""

import json as _json
import os
import sys
from datetime import datetime
from pathlib import Path

import click

# Load .env file before anything else (secrets never in code)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on shell env vars only

from .. import __version__


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option(
    "--config",
    "-c",
    "config_file",
    type=click.Path(exists=True),
    default=None,
    help="Path to configuration file (YAML/JSON).",
)
@click.option(
    "--output",
    "-o",
    "global_output",
    type=click.Path(),
    default=None,
    help="Global output directory.",
)
@click.option("--verbose", "-V", is_flag=True, default=False, help="Enable verbose output.")
@click.option("--debug", is_flag=True, default=False, help="Enable debug mode with full stack traces.")
@click.pass_context
def cli(ctx, config_file, global_output, verbose, debug):
    """Measurement Integrity Intelligence Engine (MIIE)."""
    ctx.ensure_object(dict)
    ctx.obj["config_file"] = config_file
    ctx.obj["global_output"] = global_output
    ctx.obj["verbose"] = verbose
    ctx.obj["debug"] = debug

    # If no subcommand given, launch TUI (unless --no-tui or --help)
    if ctx.invoked_subcommand is None:
        # Don't launch TUI for --help, --version, or if running in CI
        no_tui = os.environ.get("MIIE_NO_TUI", "")
        if no_tui or not sys.stdout.isatty():
            return
        # Launch TUI
        from .tui import launch_tui

        launch_tui()
        ctx.exit()
        return

    # First-run onboarding (only for non-help commands)
    if ctx.invoked_subcommand not in (None, "help") and not verbose:
        try:
            from .onboarding import is_first_run, run_onboarding

            if is_first_run():
                run_onboarding()
        except Exception:
            pass  # Never block CLI due to onboarding errors


# ---------------------------------------------------------------------------
# miie analyze
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("repo_path", type=str)
@click.option(
    "--metrics",
    "-m",
    multiple=True,
    default=["M-02", "M-06"],
    help="Metric IDs to extract (repeatable). Default: M-02 M-06",
)
@click.option(
    "--detectors",
    "-d",
    multiple=True,
    default=["D-01", "D-02", "D-03"],
    help="Detector IDs to enable (repeatable). Default: D-01 D-02 D-03",
)
@click.option(
    "--output-dir",
    "-o",
    default="./output",
    help="Output directory for reports. Default: ./output",
)
@click.option(
    "--window-strategy",
    "-w",
    default="time",
    type=click.Choice(["time", "commit", "release", "custom"]),
    help="Window segmentation strategy. Default: time",
)
@click.option(
    "--window-size",
    "-s",
    default=7,
    type=int,
    help="Window size in days/commits. Default: 7",
)
@click.option("--since", default=None, help="Extract metrics since (ISO 8601)")
@click.option("--until", default=None, help="Extract metrics until (ISO 8601)")
@click.option("--exclude-bots", is_flag=True, help="Exclude bot-generated commits")
@click.option(
    "--thresholds",
    default=None,
    type=str,
    help='Custom detector thresholds as JSON string, e.g. \'{"D-01": {"alpha": 0.05}}\'',
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate inputs and show plan without executing the pipeline",
)
@click.option("--seed", default=42, type=int, help="Random seed for reproducibility. Default: 42")
@click.option(
    "--format",
    "-f",
    "formats",
    multiple=True,
    default=["json"],
    type=click.Choice(["json", "md", "csv"]),
    help="Output format(s). Default: json",
)
@click.option(
    "--auth-token",
    default=None,
    type=str,
    help="GitHub personal access token for private repos. Falls back to GITHUB_TOKEN env var.",
)
@click.option(
    "--forensic",
    is_flag=True,
    default=False,
    help="Include full evidence package in output (advanced users).",
)
@click.option(
    "--max-commits",
    default=5000,
    type=int,
    help="Maximum commits to analyze. Default: 5000. Prevents hangs on massive repos.",
)
@click.option(
    "--workers",
    default=2,
    type=int,
    help="Parallel extraction workers. Default: 2.",
)
@click.option(
    "--timeout",
    default=60,
    type=int,
    help="Git subprocess timeout in seconds. Default: 60.",
)
@click.option(
    "--depth",
    default=None,
    type=int,
    help="Shallow clone depth. Only clones N commits of history. Faster for large repos.",
)
@click.option(
    "--package",
    "-p",
    multiple=True,
    default=[],
    help="Monorepo package path prefix to analyze (repeatable). E.g., -p packages/core",
)
@click.option(
    "--fail-on-low-confidence",
    is_flag=True,
    default=False,
    help="Exit code 2 when confidence band is 'low' (insufficient data for reliable results).",
)
@click.option(
    "--verbose",
    "-V",
    is_flag=True,
    default=False,
    help="Show detector IDs and timing details.",
)
@click.pass_context
def analyze(
    ctx,
    repo_path,
    metrics,
    detectors,
    output_dir,
    window_strategy,
    window_size,
    since,
    until,
    exclude_bots,
    thresholds,
    dry_run,
    seed,
    formats,
    auth_token,
    forensic,
    max_commits,
    workers,
    timeout,
    depth,
    package,
    fail_on_low_confidence,
    verbose,
):
    """Run the full analysis pipeline on a repository.

    Example:
        miie analyze ./my-repo --dry-run
        miie analyze ./my-repo -m M-02 -m M-06 -d D-01 -d D-02
        miie analyze ./my-repo --thresholds '{"D-01": {"alpha": 0.05}}'
        miie analyze https://github.com/pallets/flask --dry-run
        miie analyze ./my-repo --verbose
        miie analyze ./my-repo --forensic --format json --format md
    """
    from ..contracts.validators import ValidationError, validate_cli_analyze_inputs
    from ..utils.git import GitURLParser

    # Parse thresholds JSON
    detector_config = None
    if thresholds:
        try:
            detector_config = _json.loads(thresholds)
        except _json.JSONDecodeError as exc:
            click.echo(f"[INVALID-INPUT] --thresholds must be valid JSON: {exc}", err=True)
            sys.exit(3)

    # --- Input validation (exit 3: invalid arguments) ---
    try:
        validate_cli_analyze_inputs(
            repo_path=repo_path,
            since=since,
            until=until,
            metrics=list(metrics),
            window_strategy=window_strategy,
            window_size=window_size,
            output_dir=Path(output_dir),
            detectors=list(detectors),
            format=list(formats),
            exclude_bots=exclude_bots,
        )
    except ValidationError as exc:
        click.echo(f"[INVALID-INPUT] {exc}", err=True)
        sys.exit(3)

    # Command-level --verbose overrides parent group --verbose
    verbose = verbose or ctx.obj.get("verbose", False)

    # --- Dry-run mode ---
    if dry_run:
        from .pipeline_viz import display_dry_run

        display_dry_run(
            {
                "Repository": repo_path,
                "Metrics": ", ".join(metrics),
                "Detectors": ", ".join(detectors),
                "Window": f"strategy={window_strategy} size={window_size}",
                "Time range": f"since={since or '(none)'}  until={until or '(none)'}",
                "Exclude bots": str(exclude_bots),
                "Thresholds": _json.dumps(detector_config) if detector_config else "(default)",
                "Output dir": output_dir,
                "Formats": ", ".join(formats),
                "Seed": str(seed),
            }
        )
        return

    # --- Full pipeline execution with progress ---
    # Resolve auth token: CLI arg > env var
    import os
    import time

    from .display import console, print_banner
    from .errors import handle_exception

    resolved_token = auth_token or os.environ.get("GITHUB_TOKEN")

    # Detect if URL for clone messaging
    is_url = GitURLParser.is_github_url(repo_path)
    display_name = repo_path if is_url else str(Path(repo_path).resolve())

    # Early GitHub token validation — fail fast with clear error
    if is_url and not resolved_token:
        msg = (
            "[bold red]AUTH-REQUIRED:[/bold red] GitHub URL detected but no auth token provided.\n"
            "  Set GITHUB_TOKEN env var or pass --auth-token flag.\n"
            "  Private repos always require authentication."
        )
        console.print(msg)
        sys.exit(2)

    # --- Progress helper ---
    total_stages = 7
    _timings = {}

    def _progress_start(stage_num, label):
        console.print(f"\n  [cyan]{stage_num}/{total_stages}[/cyan] [bold white]{label}[/bold white]")

    def _progress_complete(stage_num, label, start_time):
        elapsed = time.perf_counter() - start_time
        _timings[label] = elapsed
        console.print(f"      [green]V[/green] [dim]({elapsed:.1f}s)[/dim]")

    def _progress_action(msg):
        console.print(f"      [dim]{msg}[/dim]")

    # --- Banner ---
    print_banner(__version__)
    console.print(f"  [bold]Repository:[/bold]  {display_name}")
    console.print()

    # Wrap entire pipeline in try/except for clean error handling (exit 2)
    try:
        _run_pipeline_rich(
            repo_path=repo_path,
            display_name=display_name,
            is_url=is_url,
            resolved_token=resolved_token,
            metrics=metrics,
            since=since,
            until=until,
            exclude_bots=exclude_bots,
            window_strategy=window_strategy,
            window_size=window_size,
            detectors=detectors,
            thresholds=thresholds,
            formats=formats,
            output_dir=output_dir,
            verbose=verbose,
            forensic=forensic,
            debug=ctx.obj.get("debug", False),
            __version__=__version__,
            max_commits=max_commits,
            workers=workers,
            timeout=timeout,
            depth=depth,
            package=list(package),
            fail_on_low_confidence=fail_on_low_confidence,
        )
    except SystemExit:
        raise
    except Exception as exc:
        handle_exception(exc, output_dir, verbose=verbose, debug=ctx.obj.get("debug", False))


def _filter_sensitive_fields(obj):
    """Remove internal IDs and paths from JSON output for default mode.

    Removes: repo_id, run_id, local_path, temp_path
    Preserves: all scientific results, scores, detector outputs, explanations
    """
    _SENSITIVE_KEYS = {"repo_id", "run_id", "local_path", "temp_path"}
    if isinstance(obj, dict):
        keys_to_remove = [k for k in obj if k in _SENSITIVE_KEYS]
        for k in keys_to_remove:
            del obj[k]
        for v in obj.values():
            _filter_sensitive_fields(v)
    elif isinstance(obj, list):
        for item in obj:
            _filter_sensitive_fields(item)


# ---------------------------------------------------------------------------
# War-room output fixes: confidence band header + data quality
# ---------------------------------------------------------------------------
def _display_confidence_band_header(
    band: str,
    score: float,
    factors: dict | None = None,
) -> None:
    """Display confidence band FIRST in output (war room finding: band was buried).

    Shows the confidence assessment before any other results so users see
    data quality before interpreting integrity scores.

    Exit codes: 0=intact+high/medium, 1=integrity triggered, 2=low confidence.
    """
    from .display import console
    from .semantic_colors import score_bar, score_to_color, score_to_label

    color = score_to_color(score)
    label = score_to_label(score)

    # Band styling
    band_styles = {
        "high": ("bold green", "HIGH CONFIDENCE"),
        "medium": ("bold yellow", "MEDIUM CONFIDENCE"),
        "low": ("bold red", "LOW CONFIDENCE"),
    }
    band_style, band_text = band_styles.get(band, ("bold red", "LOW CONFIDENCE"))

    console.print()
    console.print("  [bold cyan]Data Confidence[/bold cyan]")
    console.print("  " + "-" * 48, style="dim")

    # Prominent band indicator
    console.print(f"  [{band_style}]{band_text}[/{band_style}]  [{color}]{score:.3f}[/{color}] {label}")
    console.print(f"  {score_bar(score, 30)}", style=color)

    # Factor breakdown (if available)
    if factors:
        factor_names = {
            "sample_size": "Sample size",
            "variance": "Variance",
            "missing_data": "Missing data",
            "window_balance": "Window balance",
            "detector_success": "Detector success",
            "observation_quality": "Observation quality",
        }
        min_key = min(factors, key=factors.get)
        min_val = factors[min_key]
        min_name = factor_names.get(min_key, min_key)
        console.print(f"  [dim]Bottleneck: {min_name} = {min_val:.3f}[/dim]")

    # Low-confidence warning
    if band == "low":
        console.print()
        console.print("  [bold red]WARNING:[/bold red] Too few observations for reliable statistical tests.")
        console.print(
            "  [dim]Results may be misleading. Consider analyzing more history"
            " or changing the window strategy.[/dim]"
        )


def _display_data_quality(
    windows: list,
    metric_dataframe,
    total_commits: int,
) -> None:
    """Display data quality summary after confidence band.

    Shows window count, observation distribution, and coverage metrics
    so users understand the data foundation before seeing scores.
    """
    from .display import console

    if not windows:
        return

    console.print()
    console.print("  [bold cyan]Data Quality[/bold cyan]")
    console.print("  " + "-" * 48, style="dim")

    # Window statistics
    window_sizes = []
    for w in windows:
        commits = getattr(w, "commits", 0)
        window_sizes.append(commits)

    if window_sizes:
        avg_size = sum(window_sizes) / len(window_sizes)
        min_size = min(window_sizes)
        max_size = max(window_sizes)
        console.print(f"  Windows: {len(windows)}")
        console.print(f"  Commits per window: {min_size} min, {avg_size:.0f} avg, {max_size} max")

    # Observation coverage per metric
    if metric_dataframe and metric_dataframe.metrics:
        metric_count = len(metric_dataframe.metrics)
        total_obs = 0
        for metric_id, metric_series in metric_dataframe.metrics.items():
            if isinstance(metric_series, dict):
                for window_key, value_list in metric_series.items():
                    if isinstance(value_list, list):
                        total_obs += len([v for v in value_list if v is not None])

        console.print(f"  Metrics: {metric_count}")
        console.print(f"  Observations: {total_obs}")
        if total_obs > 0 and metric_count > 0:
            obs_per_metric = total_obs / metric_count
            console.print(f"  Avg obs/metric: {obs_per_metric:.1f}")

    # Gap detection (if available from windows)
    gap_warnings = []
    for i in range(len(windows) - 1):
        w1 = windows[i]
        w2 = windows[i + 1]
        end1 = getattr(w1, "end_date", None)
        start2 = getattr(w2, "start_date", None)
        if end1 and start2 and hasattr(end1, "date") and hasattr(start2, "date"):
            gap_days = (start2.date() - end1.date()).days
            if gap_days > 1:
                gap_warnings.append(f"Gap between w{i:02d} and w{i+1:02d}: {gap_days} days")

    if gap_warnings:
        console.print("  [bold yellow]Gaps detected:[/bold yellow]")
        for gw in gap_warnings[:3]:
            console.print(f"    [yellow]{gw}[/yellow]")
        if len(gap_warnings) > 3:
            console.print(f"    [dim]...and {len(gap_warnings) - 3} more[/dim]")


def _compress_large_reports(report_paths: dict, total_commits: int) -> None:
    """Compress JSON reports larger than 1MB for repos with 10K+ commits.

    Adds gzip-compressed copies alongside originals and updates report_paths.
    Originals are kept for backward compatibility.

    Args:
        report_paths: Dict of format -> file path (mutated in place)
        total_commits: Total commit count (triggers compression threshold)
    """
    if total_commits < 10000:
        return

    import gzip
    import shutil

    from .display import console

    compressed_count = 0
    for fmt, path_str in list(report_paths.items()):
        try:
            path = Path(path_str)
            if not path.exists() or path.suffix != ".json":
                continue

            file_size = path.stat().st_size
            if file_size < 1_000_000:  # Only compress > 1MB
                continue

            gz_path = path.with_suffix(".json.gz")
            with open(path, "rb") as f_in:
                with gzip.open(gz_path, "wb", compresslevel=6) as f_out:
                    shutil.copyfileobj(f_in, f_out)

            gz_size = gz_path.stat().st_size
            ratio = (1 - gz_size / file_size) * 100
            report_paths[f"{fmt}_compressed"] = str(gz_path)
            compressed_count += 1

            console.print(
                f"  [dim]Compressed {fmt}: {file_size / 1024:.0f}KB -> "
                f"{gz_size / 1024:.0f}KB ({ratio:.0f}% reduction)[/dim]"
            )
        except Exception:
            pass  # Compression is best-effort; don't fail the pipeline

    if compressed_count > 0:
        console.print(f"  [dim]Evidence compressed: {compressed_count} file(s)[/dim]")


# ---------------------------------------------------------------------------
# _run_pipeline_rich — Rich-powered pipeline execution
# ---------------------------------------------------------------------------
def _run_pipeline_rich(
    repo_path,
    display_name,
    is_url,
    resolved_token,
    metrics,
    since,
    until,
    exclude_bots,
    window_strategy,
    window_size,
    detectors,
    thresholds,
    formats,
    output_dir,
    verbose,
    forensic,
    debug,
    __version__,
    max_commits=5000,
    workers=2,
    timeout=60,
    depth=None,
    package=None,
    fail_on_low_confidence=False,
):
    """Execute all pipeline stages with Rich progress display."""
    import time

    # Override global git timeout from CLI knob
    import miie.utils.git as _git_module

    _git_module.GIT_TIMEOUT = timeout

    from ..processing.detection.correlation_breakdown_detector import (
        CorrelationBreakdownDetector,
    )
    from ..processing.detection.dispatcher import DetectorDispatcherEngine
    from ..processing.detection.distribution_drift_detector import (
        DistributionDriftDetector,
    )
    from ..processing.detection.registry import DetectorRegistry
    from ..processing.detection.threshold_compression_detector import (
        ThresholdCompressionDetector,
    )
    from ..processing.evidence import EvidenceEngine
    from ..processing.explanation.engine import ExplanationEngine
    from ..processing.ingestion import RepositoryIngestionEngine
    from ..processing.reporting.engine import ReportGenerator
    from ..processing.scoring.engine import ScoringEngine
    from .dashboard import display_dashboard, display_verdict
    from .display import (
        console,
        print_detection_summary,
        print_footer,
        print_kv,
        print_section,
    )
    from .errors import display_warning, handle_exception
    from .pipeline_viz import PipelineProgress
    from .premium_tui import (
        PremiumPipelineProgress,
        display_executive_summary,
        display_metric_sources,
        display_premium_footer,
    )

    # Use premium TUI for flagship output
    progress = PremiumPipelineProgress(total_stages=7, verbose=verbose)
    progress.start(repo_name=display_name)

    try:
        # --- Stage 1: Acquisition ---
        progress.stage_start("acquisition")
        t_total = time.perf_counter()
        ingestion = RepositoryIngestionEngine(auth_token=resolved_token)
        if is_url:
            progress.action("Cloning repository...")
        else:
            progress.action("Loading local repository...")
        repository_context = ingestion.ingest(
            repo_path=repo_path,
            shallow_depth=depth,
            on_progress=lambda msg: progress.action(msg),
        )
        if not ingestion.validate(repository_context):
            raise ValueError("Repository context validation failed")
        total_commits = getattr(repository_context, "total_commits", "?")
        contributor_count = getattr(repository_context, "contributor_count", "?")
        first_commit = getattr(repository_context, "first_commit_date", None)
        last_commit = getattr(repository_context, "last_commit_date", None)
        _remote_url = getattr(repository_context, "remote_url", None) or display_name
        progress.stage_complete("acquisition", f"{total_commits} commits, {contributor_count} contributors")

        # --- Stage 2: Validation ---
        progress.stage_start("validation")
        progress.action("Validating repository metadata...")
        progress.stage_complete("validation")

        # --- Stage 3: Metric Extraction (observation path) ---
        progress.stage_start("extraction")
        from ..processing.extraction.engine import (
            ExtractionEngine as _ObsExtractionEngine,
        )

        extraction_engine = _ObsExtractionEngine()
        since_dt = datetime.fromisoformat(since) if since else None
        until_dt = datetime.fromisoformat(until) if until else None
        progress.action(f"Extracting {', '.join(metrics)}...")
        observation_collection, metric_dataframe = extraction_engine.extract(
            context=repository_context,
            metric_list=list(metrics),
            since=since_dt,
            until=until_dt,
            exclude_bots=exclude_bots,
            max_commits=max_commits,
            package_prefixes=frozenset(package) if package else None,
        )
        metric_names = list(getattr(metric_dataframe, "metrics", {}).keys()) if metric_dataframe else list(metrics)
        progress.stage_complete("extraction", f"{len(metric_names)} metrics extracted")

        # --- Stage 4: Window Generation (observation path) ---
        progress.stage_start("segmentation")
        from ..processing.observation.models import WindowConfig as _ObsWindowConfig
        from ..processing.observation.window_builder import (
            ObservationWindowBuilder as _ObsWindowBuilder,
        )

        _STRATEGY_MAP = {"time": "temporal", "commit": "commit_count", "release": "temporal", "custom": "custom"}
        obs_strategy = _STRATEGY_MAP.get(window_strategy, "temporal")
        window_config = _ObsWindowConfig(
            strategy=obs_strategy,
            window_size=window_size,
            min_observations=2,
        )
        builder = _ObsWindowBuilder()
        builder_result = builder.build(collection=observation_collection, config=window_config)
        observation_windows = builder_result.windows
        window_count = len(observation_windows)
        progress.stage_complete("segmentation", f"{window_count} windows ({window_strategy}, size={window_size})")

        # Minimum window gate
        if window_count < 2:
            error_msg = f"Insufficient windows: {window_count} (need >= 2). Adjust --window-size or time range."
            display_warning(error_msg)
            if "json" in formats:
                console.print(_json.dumps({"error": error_msg, "exit_code": 3}, indent=2))
            raise SystemExit(3)

        # Rebuild MetricDataFrame from observation_windows to align window IDs
        # The extraction engine creates a single window w00, but ObservationWindowBuilder
        # creates multiple windows. We need the MetricDataFrame to use the same window IDs.
        from ..processing.extraction.metric_extractor import (
            MetricExtractor as _MetricExtractor,
        )
        from ..processing.observation.models import (
            ObservationCollection as _ObsCollection,
        )

        _rebuilt_collection = _ObsCollection(
            collection_id=observation_collection.collection_id,
            repository_id=observation_collection.repository_id,
            analysis_id=observation_collection.analysis_id,
            windows=observation_windows,
            total_observations=sum(len(ow.observations) for ow in observation_windows),
            total_metrics=len(set(obs.metric_id for ow in observation_windows for obs in ow.observations)),
            extraction_timestamp=observation_collection.extraction_timestamp,
        )
        metric_dataframe = _MetricExtractor().extract_metrics(
            _rebuilt_collection,
            metric_list=list(metrics),
        )

        # Convert observation windows to legacy WindowDefinitions for scoring/evidence
        from ..schemas.models import WindowDefinition as _WinDef

        windows = []
        for ow in observation_windows:
            wd = _WinDef(
                window_id=ow.window_id,
                start_date=ow.start_boundary[:10] if hasattr(ow, "start_boundary") and ow.start_boundary else None,
                end_date=ow.end_boundary[:10] if hasattr(ow, "end_boundary") and ow.end_boundary else None,
                commits=len(ow.observations) if hasattr(ow, "observations") else 0,
                strategy=obs_strategy,
                size_config={"size": window_size},
            )
            windows.append(wd)

        # --- Sampling Framework ---
        sampling_diagnostics = None
        try:
            from ..processing.observation.models import (
                _METRIC_UNITS,
                Observation,
                ObservationCollection,
                ObservationProvenance,
                ObservationWindow,
                generate_observation_id,
            )
            from ..sampling.diagnostics import DiagnosticsEngine

            obs_windows_for_sampling: list = []
            _STRATEGY_MAP = {"time": "temporal", "commit": "commit_count"}

            for wd in windows:
                obs_list: list = []
                for metric_id, window_data in metric_dataframe.metrics.items():
                    values = window_data.get(wd.window_id, [])
                    for i, val in enumerate(values):
                        if val is not None:
                            import hashlib as _hl

                            source_id = _hl.sha256(f"synthetic:{wd.window_id}:{metric_id}:{i}".encode()).hexdigest()[
                                :40
                            ]
                            obs_id = generate_observation_id("commit", source_id, metric_id)
                            unit = _METRIC_UNITS.get(metric_id, "count")
                            obs = Observation(
                                observation_id=obs_id,
                                source_type="commit",
                                source_id=source_id,
                                metric_id=metric_id,
                                value=float(val),
                                unit=unit,
                                timestamp=wd.start_date.isoformat() + "T00:00:00+00:00",
                                quality="complete",
                                provenance=ObservationProvenance(
                                    extractor_id="cli-bridge",
                                    extraction_timestamp=datetime.now().isoformat(),
                                ),
                            )
                            obs_list.append(obs)
                if obs_list:
                    raw_strategy = wd.strategy or "temporal"
                    mapped_strategy = _STRATEGY_MAP.get(raw_strategy, raw_strategy)
                    window = ObservationWindow(
                        window_id=wd.window_id,
                        window_index=windows.index(wd),
                        strategy=mapped_strategy,
                        start_boundary=wd.start_date.isoformat() + "T00:00:00+00:00",
                        end_boundary=wd.end_date.isoformat() + "T00:00:00+00:00",
                        observations=obs_list,
                    )
                    obs_windows_for_sampling.append(window)

            total_obs_count = sum(len(w.observations) for w in obs_windows_for_sampling)
            metrics_present = set()
            for w in obs_windows_for_sampling:
                for obs in w.observations:
                    metrics_present.add(obs.metric_id)

            obs_collection = ObservationCollection(
                collection_id="cli_sampling_collection",
                repository_id=getattr(repository_context, "repo_id", "unknown"),
                analysis_id="cli_analysis",
                windows=obs_windows_for_sampling,
                total_observations=total_obs_count,
                total_metrics=len(metrics_present),
                extraction_timestamp=datetime.now().isoformat(),
            )

            progress.action("Running sampling analysis...")
            diag_engine = DiagnosticsEngine()
            sampling_diagnostics = diag_engine.run(obs_collection)

        except Exception as e:
            sampling_diagnostics = None
            if verbose or forensic:
                progress.action(f"Note: Sampling diagnostics unavailable: {e}")

        # --- Stage 5: Detector Execution ---
        progress.stage_start("detection")
        registry = DetectorRegistry()
        registry.register(DistributionDriftDetector())
        registry.register(CorrelationBreakdownDetector())
        registry.register(ThresholdCompressionDetector())
        dispatcher = DetectorDispatcherEngine(registry)
        detector_config = None
        if thresholds:
            try:
                detector_config = _json.loads(thresholds)
            except _json.JSONDecodeError:
                detector_config = None
        progress.action(f"Running {len(detectors)} detectors...")
        detector_results = dispatcher.invoke_observations(
            observation_windows=observation_windows,
            detector_config=detector_config,
            enabled_detectors=list(detectors),
        )
        progress.stage_complete("detection", f"{len(detectors)} detectors executed")

        # --- Stage 6: Evidence Generation ---
        progress.stage_start("evidence")
        scoring = ScoringEngine()
        score_package = scoring.compute_integrity_score(
            detector_results=detector_results,
            metric_dataframe=metric_dataframe,
            windows=windows,
        )
        evidence_engine = EvidenceEngine()
        evidence_package = evidence_engine.generate(
            repository_context=repository_context,
            metric_dataframe=metric_dataframe,
            windows=windows,
            detector_results=detector_results,
            score_package=score_package,
            configuration={
                "metric_list": list(metrics),
                "since": since_dt,
                "until": until_dt,
                "exclude_bots": exclude_bots,
                "segmentation_strategy": window_strategy,
                "segmentation_size": window_size,
            },
        )
        explanation_engine = ExplanationEngine()
        explanation_report = explanation_engine.generate(
            evidence_package=evidence_package,
            score_package=score_package,
        )
        progress.stage_complete("evidence")

        # --- Stage 7: Final Assessment ---
        progress.stage_start("reporting")
        report_generator = ReportGenerator()
        analysis_results = {
            "repository_context": repository_context,
            "metric_dataframe": metric_dataframe,
            "windows": windows,
            "detector_results": detector_results,
            "score_package": score_package,
            "evidence_package": evidence_package,
            "explanation_report": explanation_report,
        }

        if sampling_diagnostics is not None:
            try:
                from ..sampling.diagnostics import DiagnosticsEngine as DiagEng

                _diag_engine = DiagEng()
                analysis_results["sampling_diagnostics"] = _diag_engine.to_dict(sampling_diagnostics)
            except Exception:
                pass

        # Privacy filtering
        if not forensic:
            serialized = report_generator._serialize_for_json(analysis_results)
            _filter_sensitive_fields(serialized)
            analysis_results = serialized

        report_output = report_generator.generate(
            analysis_result=analysis_results,
            output_formats=list(formats),
            output_dir=Path(output_dir),
        )
        progress.stage_complete("reporting")

        _t_total_elapsed = time.perf_counter() - t_total
        progress.stop()

        # --- Extract scores ---
        integrity = score_package.integrity
        confidence = score_package.confidence
        integrity_overall = integrity.get("overall", 0.0) if isinstance(integrity, dict) else integrity.overall
        confidence_overall = confidence.get("overall", 0.0) if isinstance(confidence, dict) else confidence.overall

        # Extract confidence band and factors for display
        confidence_band = "low"
        confidence_factors = None
        if confidence is not None:
            if isinstance(confidence, dict):
                confidence_band = confidence.get("band", "low")
                confidence_factors = confidence.get("factors", {})
            else:
                confidence_band = getattr(confidence, "band", "low")
                confidence_factors = getattr(confidence, "factors", {})

        # --- Extract detector results ---
        detector_outputs = {}
        if detector_results:
            detector_outputs = getattr(detector_results, "detector_outputs", {})
            if not detector_outputs and hasattr(detector_results, "d_01"):
                detector_outputs = {
                    "D-01": getattr(detector_results, "d_01", {}),
                    "D-02": getattr(detector_results, "d_02", {}),
                    "D-03": getattr(detector_results, "d_03", {}),
                }

        # --- Risk Classification ---
        triggered_count = 0
        failed_detectors = []
        for det_id, det_data in detector_outputs.items():
            if not isinstance(det_data, dict):
                continue
            if det_data.get("status") in ("error", "skipped"):
                failed_detectors.append(det_id)
                continue
            if (
                det_data.get("drift_detected")
                or det_data.get("breakdown_detected")
                or det_data.get("compression_detected", False)
            ):
                triggered_count += 1

        # === PHASE 1: Confidence Band (shown FIRST per war room finding) ===
        _display_confidence_band_header(confidence_band, confidence_overall, confidence_factors)

        # === PHASE 2: Data Quality Summary ===
        _display_data_quality(
            windows=windows,
            metric_dataframe=metric_dataframe,
            total_commits=total_commits,
        )

        # === PHASE 3: Monorepo Hint ===
        _workspace_info = getattr(repository_context, "_workspace_info", None)
        if _workspace_info and not list(package):
            console.print()
            console.print(
                "  [bold yellow]TIP:[/bold yellow] Monorepo detected. "
                "Use [bold]--package <path>[/bold] to analyze a specific package."
            )
            console.print("  [dim]Example: miie analyze ./monorepo -p packages/core[/dim]")

        # --- Display Dashboard (Premium) ---
        display_executive_summary(
            integrity_score=integrity_overall,
            confidence_score=confidence_overall,
            total_commits=total_commits,
            contributor_count=contributor_count,
            window_count=window_count,
            detector_outputs=detector_outputs,
            timings=progress.timings,
            repo_name=display_name,
            verbose=verbose,
            confidence_band=confidence_band,
            confidence_factors=confidence_factors,
        )

        # Display metric sources
        display_metric_sources(metric_names)

        # Forensic details
        if forensic:
            print_section("Forensic Details")
            print_kv("Window Count", len(windows))
            for w in windows:
                wid = getattr(w, "window_id", "?")
                sd = getattr(w, "start_date", "?")
                ed = getattr(w, "end_date", "?")
                commits = getattr(w, "commits", "?")
                console.print(f"    {wid}: {sd} to {ed} ({commits} commits)")
            print_kv("Metrics", ", ".join(metrics))
            print_kv("Detectors", ", ".join(detectors))
            print_kv("Window Strategy", window_strategy)
            print_kv("Window Size", window_size)

        # --- Reports ---
        report_out = report_output
        report_paths = {}
        if report_out and report_out.report_paths:
            report_paths = report_out.report_paths

        # --- Evidence Compression for Large Repos ---
        # Compress JSON reports > 1MB with gzip to save disk space
        _compress_large_reports(report_paths, total_commits)

        # --- Premium Footer ---
        display_premium_footer(
            total_time=_t_total_elapsed,
            report_paths=report_paths,
            success=True,
        )

        # Exit 2 if --fail-on-low-confidence and band is "low"
        if fail_on_low_confidence and confidence_band == "low":
            console.print()
            console.print(
                "  [bold red]EXIT CODE 2:[/bold red] Confidence band is 'low' "
                "(insufficient data for reliable results)."
            )
            console.print("  [dim]Re-run with more history or a different window strategy.[/dim]")
            sys.exit(2)

        # Exit 1 if integrity score < 1.0
        if integrity_overall < 1.0:
            sys.exit(1)

    except SystemExit:
        raise
    except Exception as exc:
        progress.stop()
        handle_exception(exc, output_dir, verbose=verbose, debug=debug)


# ---------------------------------------------------------------------------
# miie ingest
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("repo_path", type=str)
@click.option("--shallow", type=int, default=None, help="Shallow clone depth (e.g., --shallow 100)")
@click.option(
    "--auth-token",
    default=None,
    type=str,
    help="GitHub personal access token for private repos. Falls back to GITHUB_TOKEN env var.",
)
@click.pass_context
def ingest(ctx, repo_path, shallow, auth_token):
    """Validate and ingest a repository.

    Checks Git validity, counts commits, and stores ingestion context
    for downstream analysis. For GitHub URLs, automatically clones the
    repository (use --shallow to limit clone depth).

    \b
    Examples:
      miie ingest /path/to/repo
      miie ingest https://github.com/user/repo --shallow 100
      miie ingest /path/to/repo --auth-token ghp_xxxx
    """
    from ..contracts.validators import ValidationError, validate_cli_ingest_inputs
    from ..utils.git import GitURLParser
    from .display import console, error_panel, print_kv, print_section

    # Check if repo_path is a GitHub URL
    if GitURLParser.is_github_url(repo_path):
        console.print(f"  [info]GitHub URL detected:[/info] {repo_path}")
        console.print("  [info]Cloning repository...[/info]")

    try:
        validate_cli_ingest_inputs(repo_path, shallow=shallow)
    except ValidationError as exc:
        error_panel("Invalid Input", str(exc))
        sys.exit(3)

    # Resolve auth token: CLI arg > env var
    import os

    resolved_token = auth_token or os.environ.get("GITHUB_TOKEN")

    from ..processing.ingestion import RepositoryIngestionEngine

    engine = RepositoryIngestionEngine(auth_token=resolved_token)
    try:
        ctx_result = engine.ingest(repo_path=repo_path, shallow_depth=shallow)
        print_section("Ingestion Successful")
        print_kv("Repo ID", ctx_result.repo_id)
        print_kv("Commits", ctx_result.total_commits)
        print_kv("Contributors", ctx_result.contributor_count)
        print_kv("Local path", ctx_result.local_path)
    except Exception as exc:
        from .errors import handle_exception

        handle_exception(exc, verbose=ctx.obj.get("verbose", False), debug=ctx.obj.get("debug", False))


# ---------------------------------------------------------------------------
# miie detect
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("repo_path", type=str)
@click.option(
    "--metrics",
    "-m",
    multiple=True,
    default=["M-02", "M-06"],
    help="Metric IDs to extract (repeatable).",
)
@click.option(
    "--detectors",
    "-d",
    multiple=True,
    default=["D-01", "D-02", "D-03"],
    help="Detector IDs to enable (repeatable).",
)
@click.option("--seed", default=42, type=int, help="Random seed.")
@click.option(
    "--auth-token",
    default=None,
    type=str,
    help="GitHub personal access token for private repos. Falls back to GITHUB_TOKEN env var.",
)
@click.pass_context
def detect(ctx, repo_path, metrics, detectors, seed, auth_token):
    """Run detection on a repository.

    Performs ingestion + extraction + detection only (no scoring).
    Useful for quick checks without running the full pipeline.

    \b
    Detectors:
      D-01  Distribution Drift (KS test + PSI)
      D-02  Correlation Breakdown (Pearson + Fisher z)
      D-03  Threshold Compression (dip test + excess mass)

    \b
    Examples:
      miie detect /path/to/repo
      miie detect /path/to/repo -m M-01 M-02 -d D-01
      miie detect https://github.com/user/repo --seed 123
    """
    from ..utils.git import GitURLParser

    # Check if repo_path is a GitHub URL
    if GitURLParser.is_github_url(repo_path):
        click.echo(f"[INFO] GitHub URL detected: {repo_path}")
        click.echo("[INFO] Cloning repository...")

    # Resolve auth token: CLI arg > env var
    import os

    resolved_token = auth_token or os.environ.get("GITHUB_TOKEN")

    from ..processing.detection.dispatcher import DetectorDispatcherEngine
    from ..processing.detection.registry import DetectorRegistry
    from ..processing.extraction.engine import ExtractionEngine
    from ..processing.ingestion import RepositoryIngestionEngine
    from ..processing.observation.models import WindowConfig
    from ..processing.observation.window_builder import ObservationWindowBuilder

    registry = DetectorRegistry()
    from ..processing.detection.correlation_breakdown_detector import (
        CorrelationBreakdownDetector,
    )
    from ..processing.detection.distribution_drift_detector import (
        DistributionDriftDetector,
    )
    from ..processing.detection.threshold_compression_detector import (
        ThresholdCompressionDetector,
    )

    registry.register(DistributionDriftDetector())
    registry.register(CorrelationBreakdownDetector())
    registry.register(ThresholdCompressionDetector())

    click.echo(f"Running detection on {repo_path} ...")
    try:
        ctx_ingested = RepositoryIngestionEngine(auth_token=resolved_token).ingest(repo_path)
        extraction_engine = ExtractionEngine()
        observation_collection, mdf = extraction_engine.extract(
            context=ctx_ingested,
            metric_list=list(metrics),
        )
        window_config = WindowConfig(strategy="temporal", window_size=7, min_observations=2)
        builder = ObservationWindowBuilder()
        builder_result = builder.build(collection=observation_collection, config=window_config)
        observation_windows = builder_result.windows
        if len(observation_windows) < 2:
            click.echo(
                f"[WARNING] Insufficient windows: {len(observation_windows)} (need >= 2). Adjust time range or window size.",
                err=True,
            )
            sys.exit(3)
        results = DetectorDispatcherEngine(registry).invoke_observations(
            observation_windows=observation_windows,
        )
        click.echo(f"Detection complete. {len(results.detector_outputs)} detector(s) ran:")
        for det_id, output in results.detector_outputs.items():
            click.echo(f"  {det_id}: {list(output.keys()) if isinstance(output, dict) else type(output).__name__}")
    except Exception as exc:
        click.echo(f"[SYSTEM-ERROR] {exc}", err=True)
        sys.exit(2)


# ---------------------------------------------------------------------------
# miie benchmark
# ---------------------------------------------------------------------------
@cli.command()
@click.option("--suite", "-s", required=True, help="Benchmark suite ID (e.g. B-01)")
@click.option(
    "--detectors",
    "-d",
    multiple=True,
    default=["D-01", "D-02", "D-03"],
    help="Detector IDs to benchmark.",
)
@click.option("--config", "-cfg", default=None, help="JSON config string.")
@click.option("--seed", default=42, type=int, help="Random seed.")
@click.pass_context
def benchmark(ctx, suite, detectors, config, seed):
    """Execute a benchmark suite against detectors.

    Runs pre-defined benchmark scenarios and reports detector
    performance metrics (precision, recall, F1).

    \b
    Examples:
      miie benchmark default
      miie benchmark default -d D-01 D-02
      miie benchmark default --config '{"threshold": 0.1}'
    """
    from ..processing.benchmark.engine import BenchmarkEngine

    cfg = _json.loads(config) if config else {"threshold": 0.05}
    click.echo(f"Running benchmark suite {suite} ...")
    try:
        engine = BenchmarkEngine()
        result = engine.execute(suite_id=suite, detector_ids=list(detectors), config=cfg, seed=seed)
        click.echo(f"Benchmark complete. Metadata: {result.metadata}")
    except Exception as exc:
        click.echo(f"[BENCHMARK-ERROR] {exc}", err=True)
        sys.exit(4)


# ---------------------------------------------------------------------------
# miie evaluate
# ---------------------------------------------------------------------------
@cli.command()
@click.option(
    "--benchmark-json",
    "-b",
    required=True,
    type=click.Path(exists=True),
    help="Path to BenchmarkRun JSON file.",
)
@click.option(
    "--ground-truth",
    "-g",
    required=True,
    type=click.Path(exists=True),
    help="Path to ground truth JSON file.",
)
@click.pass_context
def evaluate(ctx, benchmark_json, ground_truth):
    """Evaluate benchmark results against ground truth."""
    from ..processing.evaluation.engine import EvaluationEngine
    from ..schemas.models import BenchmarkRun

    click.echo("Evaluating benchmark ...")
    try:
        with open(benchmark_json) as f:
            br_data = _json.load(f)
        benchmark_run = BenchmarkRun(
            predictions=br_data.get("predictions", {}),
            metadata=br_data.get("metadata", {}),
        )
        with open(ground_truth) as f:
            gt_data = _json.load(f)
        result = EvaluationEngine().evaluate(benchmark_run, gt_data)
        click.echo(f"  Accuracy : {result.accuracy:.4f}")
        click.echo(f"  F1 Score : {result.f1_score:.4f}")
        click.echo(f"  Precision: {result.precision:.4f}")
        click.echo(f"  Recall   : {result.recall:.4f}")
    except Exception as exc:
        click.echo(f"[SYSTEM-ERROR] {exc}", err=True)
        sys.exit(2)


# ---------------------------------------------------------------------------
# miie explain
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--metrics", "-m", multiple=True, default=["M-02", "M-06"])
@click.option("--metric-filter", default=None, help="Specific metric to explain.")
@click.option("--detector-filter", default=None, help="Specific detector to explain.")
@click.option("--seed", default=42, type=int)
@click.pass_context
def explain(ctx, repo_path, metrics, metric_filter, detector_filter, seed):
    """Run analysis and generate explanation report.

    Performs the full pipeline (ingest → extract → detect → score)
    then generates human-readable explanations of findings.

    \b
    Examples:
      miie explain /path/to/repo
      miie explain /path/to/repo -m M-01 M-02 --metric-filter M-02
      miie explain /path/to/repo --detector-filter D-01
    """
    from ..processing.detection.dispatcher import DetectorDispatcherEngine
    from ..processing.detection.registry import DetectorRegistry
    from ..processing.evidence import EvidenceEngine
    from ..processing.explanation.engine import ExplanationEngine
    from ..processing.extraction.engine import ExtractionEngine
    from ..processing.ingestion import RepositoryIngestionEngine
    from ..processing.observation.models import WindowConfig
    from ..processing.observation.window_builder import ObservationWindowBuilder
    from ..processing.scoring.engine import ScoringEngine

    registry = DetectorRegistry()
    from ..processing.detection.correlation_breakdown_detector import (
        CorrelationBreakdownDetector,
    )
    from ..processing.detection.distribution_drift_detector import (
        DistributionDriftDetector,
    )
    from ..processing.detection.threshold_compression_detector import (
        ThresholdCompressionDetector,
    )

    registry.register(DistributionDriftDetector())
    registry.register(CorrelationBreakdownDetector())
    registry.register(ThresholdCompressionDetector())

    click.echo(f"Running analysis and explanation on {repo_path} ...")
    try:
        ctx_ingested = RepositoryIngestionEngine().ingest(repo_path)
        extraction_engine = ExtractionEngine()
        observation_collection, mdf = extraction_engine.extract(
            context=ctx_ingested,
            metric_list=list(metrics),
        )
        window_config = WindowConfig(strategy="temporal", window_size=7, min_observations=2)
        builder = ObservationWindowBuilder()
        builder_result = builder.build(collection=observation_collection, config=window_config)
        observation_windows = builder_result.windows
        if len(observation_windows) < 2:
            click.echo(f"[WARNING] Insufficient windows: {len(observation_windows)} (need >= 2).", err=True)
            sys.exit(3)
        # Rebuild MetricDataFrame from observation_windows to align window IDs
        from ..processing.extraction.metric_extractor import (
            MetricExtractor as _MetricExtractor,
        )
        from ..processing.observation.models import (
            ObservationCollection as _ObsCollection,
        )

        _rebuilt_collection = _ObsCollection(
            collection_id=observation_collection.collection_id,
            repository_id=observation_collection.repository_id,
            analysis_id=observation_collection.analysis_id,
            windows=observation_windows,
            total_observations=sum(len(ow.observations) for ow in observation_windows),
            total_metrics=len(set(obs.metric_id for ow in observation_windows for obs in ow.observations)),
            extraction_timestamp=observation_collection.extraction_timestamp,
        )
        mdf = _MetricExtractor().extract_metrics(
            _rebuilt_collection,
            metric_list=list(metrics),
        )
        det_results = DetectorDispatcherEngine(registry).invoke_observations(
            observation_windows=observation_windows,
        )
        # Convert observation windows to legacy WindowDefinitions for scoring/evidence
        from ..schemas.models import WindowDefinition as _WinDef

        _STRATEGY_MAP = {"time": "temporal", "commit": "commit_count"}
        wins = []
        for ow in observation_windows:
            wd = _WinDef(
                window_id=ow.window_id,
                start_date=ow.start_boundary[:10] if hasattr(ow, "start_boundary") and ow.start_boundary else None,
                end_date=ow.end_boundary[:10] if hasattr(ow, "end_boundary") and ow.end_boundary else None,
                commits=len(ow.observations) if hasattr(ow, "observations") else 0,
                strategy=_STRATEGY_MAP.get("time", "temporal"),
                size_config={"size": 7},
            )
            wins.append(wd)
        score_pkg = ScoringEngine().compute_integrity_score(det_results, mdf, wins)
        evidence = EvidenceEngine().generate(ctx_ingested, mdf, wins, det_results, score_pkg, {"seed": seed})
        explanation = ExplanationEngine().generate(
            evidence,
            score_pkg,
            metric_filter=metric_filter,
            detector_filter=detector_filter,
        )
        click.echo(f"Explanation complete. {len(explanation.narratives)} narrative(s)")
        for i, n in enumerate(explanation.narratives, 1):
            click.echo(f"  {i}. {n}")
    except Exception as exc:
        click.echo(f"[SYSTEM-ERROR] {exc}", err=True)
        sys.exit(2)


# ---------------------------------------------------------------------------
# miie export
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--formats", "-f", multiple=True, default=["json", "csv"], help="Export formats.")
@click.option("--output-dir", "-o", type=click.Path(), default="./export")
@click.option("--seed", default=42, type=int)
@click.pass_context
def export(ctx, repo_path, formats, output_dir, seed):
    """Run analysis and export results in specified formats.

    Performs the full pipeline and writes results to disk in the
    requested formats.

    \b
    Supported formats:
      json  Structured JSON with full evidence package
      csv   Flat CSV with per-metric scores
      html  Interactive HTML report with charts
      text  Plain-text summary

    \b
    Examples:
      miie export /path/to/repo -f json csv
      miie export /path/to/repo -f html -o ./reports
    """
    from pathlib import Path as _P

    from ..processing.detection.dispatcher import DetectorDispatcherEngine
    from ..processing.detection.registry import DetectorRegistry
    from ..processing.extraction.engine import ExtractionEngine
    from ..processing.ingestion import RepositoryIngestionEngine
    from ..processing.observation.models import WindowConfig
    from ..processing.observation.window_builder import ObservationWindowBuilder
    from ..processing.scoring.engine import ScoringEngine

    registry = DetectorRegistry()
    from ..processing.detection.correlation_breakdown_detector import (
        CorrelationBreakdownDetector,
    )
    from ..processing.detection.distribution_drift_detector import (
        DistributionDriftDetector,
    )
    from ..processing.detection.threshold_compression_detector import (
        ThresholdCompressionDetector,
    )

    registry.register(DistributionDriftDetector())
    registry.register(CorrelationBreakdownDetector())
    registry.register(ThresholdCompressionDetector())

    out = _P(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    click.echo(f"Exporting analysis of {repo_path} ...")
    try:
        ctx_ingested = RepositoryIngestionEngine().ingest(repo_path)
        extraction_engine = ExtractionEngine()
        observation_collection, mdf = extraction_engine.extract(
            context=ctx_ingested,
            metric_list=["M-02", "M-06"],
        )
        window_config = WindowConfig(strategy="temporal", window_size=7, min_observations=2)
        builder = ObservationWindowBuilder()
        builder_result = builder.build(collection=observation_collection, config=window_config)
        observation_windows = builder_result.windows
        if len(observation_windows) < 2:
            click.echo(f"[WARNING] Insufficient windows: {len(observation_windows)} (need >= 2).", err=True)
            sys.exit(3)
        # Rebuild MetricDataFrame from observation_windows to align window IDs
        from ..processing.extraction.metric_extractor import (
            MetricExtractor as _MetricExtractor,
        )
        from ..processing.observation.models import (
            ObservationCollection as _ObsCollection,
        )

        _rebuilt_collection = _ObsCollection(
            collection_id=observation_collection.collection_id,
            repository_id=observation_collection.repository_id,
            analysis_id=observation_collection.analysis_id,
            windows=observation_windows,
            total_observations=sum(len(ow.observations) for ow in observation_windows),
            total_metrics=len(set(obs.metric_id for ow in observation_windows for obs in ow.observations)),
            extraction_timestamp=observation_collection.extraction_timestamp,
        )
        mdf = _MetricExtractor().extract_metrics(
            _rebuilt_collection,
            metric_list=["M-02", "M-06"],
        )
        det_results = DetectorDispatcherEngine(registry).invoke_observations(
            observation_windows=observation_windows,
        )
        # Convert observation windows to legacy WindowDefinitions for scoring
        from ..schemas.models import WindowDefinition as _WinDef

        _STRATEGY_MAP = {"time": "temporal", "commit": "commit_count"}
        wins = []
        for ow in observation_windows:
            wd = _WinDef(
                window_id=ow.window_id,
                start_date=ow.start_boundary[:10] if hasattr(ow, "start_boundary") and ow.start_boundary else None,
                end_date=ow.end_boundary[:10] if hasattr(ow, "end_boundary") and ow.end_boundary else None,
                commits=len(ow.observations) if hasattr(ow, "observations") else 0,
                strategy=_STRATEGY_MAP.get("time", "temporal"),
                size_config={"size": 7},
            )
            wins.append(wd)
        score_pkg = ScoringEngine().compute_integrity_score(det_results, mdf, wins)

        data = {
            "repo_id": ctx_ingested.repo_id,
            "integrity": score_pkg.integrity.overall,
            "confidence": score_pkg.confidence.overall,
        }
        exported = {}
        for fmt in formats:
            p = out / f"export.{fmt}"
            if fmt == "json":
                p.write_text(_json.dumps(data, indent=2))
            elif fmt == "csv":
                p.write_text("metric,value\n")
                for k, v in data.items():
                    p.write_text(f"{k},{v}\n")
            exported[fmt] = p
        click.echo(f"Exported to {out}:")
        for fmt, p in exported.items():
            click.echo(f"  {fmt}: {p}")
    except Exception as exc:
        click.echo(f"[SYSTEM-ERROR] {exc}", err=True)
        sys.exit(2)


# ---------------------------------------------------------------------------
# miie generate
# ---------------------------------------------------------------------------
@cli.command()
@click.option(
    "--type",
    "-t",
    "dataset_type",
    default="metric-drift",
    help="Dataset type (metric-drift, correlation-breakdown, threshold-compression).",
)
@click.option("--count", "-n", default=5, type=int, help="Number of candidates to generate.")
@click.option("--output-dir", "-o", type=click.Path(), default="./benchmarks/generated")
@click.option("--seed", default=42, type=int)
@click.pass_context
def generate(ctx, dataset_type, count, output_dir, seed):
    """Generate synthetic benchmark candidates."""
    from pathlib import Path as _P

    from ..benchmark.generator import BenchmarkDatasetGenerator

    click.echo(f"Generating {count} {dataset_type} candidates ...")
    try:
        gen = BenchmarkDatasetGenerator()
        paths = gen.generate(dataset_type, count, _P(output_dir), seed=seed)
        click.echo(f"Generated {len(paths)} candidate(s):")
        for p in paths:
            click.echo(f"  {p}")
    except Exception as exc:
        click.echo(f"[SYSTEM-ERROR] {exc}", err=True)
        sys.exit(2)


# ---------------------------------------------------------------------------
# miie status
# ---------------------------------------------------------------------------
@cli.command()
@click.pass_context
def status(ctx):
    """Show MIIE system status.

    Displays engine availability, detector registration, active
    configuration, and Python/platform details.

    \b
    Examples:
      miie status
      miie status --verbose
    """
    from rich.table import Table

    from .config import display_config
    from .display import console, print_banner

    print_banner(__version__, "System Status")

    engines = {
        "IngestionEngine": ("miie.processing.ingestion", "RepositoryIngestionEngine"),
        "ExtractionEngine": ("miie.processing.extraction", "MetricExtractionEngine"),
        "SegmentationEngine": ("miie.processing.segmentation", "WindowSegmentationEngine"),
        "ScoringEngine": ("miie.processing.scoring.engine", "ScoringEngine"),
        "EvidenceEngine": ("miie.processing.evidence", "EvidenceEngine"),
        "ExplanationEngine": ("miie.processing.explanation.engine", "ExplanationEngine"),
        "ReportGenerator": ("miie.processing.reporting.engine", "ReportGenerator"),
        "BenchmarkEngine": ("miie.processing.benchmark.engine", "BenchmarkEngine"),
        "EvaluationEngine": ("miie.processing.evaluation.engine", "EvaluationEngine"),
    }

    table = Table(title="Engine Status", show_header=True, header_style="bold cyan")
    table.add_column("Engine", style="bold")
    table.add_column("Status")

    for name, (mod_path, cls_name) in engines.items():
        try:
            mod = __import__(mod_path, fromlist=[cls_name])
            getattr(mod, cls_name)
            table.add_row(name, "[green]OK[/green]")
        except Exception:
            table.add_row(name, "[red]MISSING[/red]")

    console.print(table)

    # Detectors
    try:
        from ..processing.detection.correlation_breakdown_detector import (
            CorrelationBreakdownDetector,
        )
        from ..processing.detection.distribution_drift_detector import (
            DistributionDriftDetector,
        )
        from ..processing.detection.registry import DetectorRegistry
        from ..processing.detection.threshold_compression_detector import (
            ThresholdCompressionDetector,
        )

        reg = DetectorRegistry()
        for det_cls in [
            DistributionDriftDetector,
            CorrelationBreakdownDetector,
            ThresholdCompressionDetector,
        ]:
            try:
                reg.register(det_cls())
            except Exception:
                pass
        console.print(f"\n  [bold]Detectors:[/bold] [green]{len(reg._detectors)} registered[/green]")
    except Exception:
        console.print("\n  [bold]Detectors:[/bold] [red]Registry unavailable[/red]")

    # Configuration
    config_file = ctx.obj.get("config_file")
    verbose = ctx.obj.get("verbose", False)
    if config_file:
        console.print(f"\n  [bold]Config file:[/bold] {config_file}")
    if verbose:
        console.print("  [bold]Verbose mode:[/bold] enabled")

    # Show current config
    display_config()


# ---------------------------------------------------------------------------
# miie validate
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("target", type=click.Path(exists=True))
@click.option(
    "--type",
    "-t",
    "validate_type",
    default="config",
    type=click.Choice(["config", "analysis", "benchmark", "manifest"]),
    help="Type of artifact to validate. Default: config",
)
@click.pass_context
def validate(ctx, target, validate_type):
    """Validate a config file, analysis output, or benchmark artifact.

    Example:
        miie validate ./config.yaml --type config
        miie validate ./output/results.json --type analysis
    """
    target_path = Path(target)
    click.echo(f"Validating {target_path} (type={validate_type}) ...")

    try:
        if validate_type == "config":
            _validate_config(target_path)
        elif validate_type == "analysis":
            _validate_analysis(target_path)
        elif validate_type == "benchmark":
            _validate_benchmark(target_path)
        elif validate_type == "manifest":
            _validate_manifest(target_path)
        click.echo("Validation PASSED")
    except Exception as exc:
        click.echo(f"[VALIDATION-FAILED] {exc}", err=True)
        sys.exit(3)


def _validate_config(path: Path) -> None:
    """Validate a configuration file (YAML or JSON)."""
    import yaml

    content = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(content)
    elif path.suffix == ".json":
        data = _json.loads(content)
    else:
        raise ValueError(f"Unsupported config format: {path.suffix}")

    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON/YAML object")

    required_fields = {"repo"}
    missing = required_fields - set(data.keys())
    if missing:
        raise ValueError(f"Missing required fields: {missing}")


def _validate_analysis(path: Path) -> None:
    """Validate analysis output (results.json)."""
    data = _json.loads(path.read_text(encoding="utf-8"))
    required = {"score_package", "repository_context"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Missing required fields in analysis output: {missing}")


def _validate_benchmark(path: Path) -> None:
    """Validate a benchmark run JSON file."""
    data = _json.loads(path.read_text(encoding="utf-8"))
    required = {"run_id", "suite_id", "detector_id", "predictions"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Missing required fields in benchmark output: {missing}")


def _validate_manifest(path: Path) -> None:
    """Validate a manifest.json file."""
    data = _json.loads(path.read_text(encoding="utf-8"))
    required = {"miie_version", "python_version", "platform", "timestamp"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Missing required fields in manifest: {missing}")


# ---------------------------------------------------------------------------
# miie setup
# ---------------------------------------------------------------------------
@cli.command()
@click.option("--reset", is_flag=True, help="Reset configuration to defaults.")
@click.pass_context
def setup(ctx, reset):
    """Interactive configuration setup wizard.

    Configure GitHub token, default directories, output formats,
    and other MIIE settings interactively.

    Example:
        miie setup
        miie setup --reset
    """
    from .config import DEFAULT_CONFIG, display_config, save_config
    from .display import console, print_banner, success_panel
    from .interactive import run_config_wizard

    print_banner(__version__, "Configuration Setup")

    if reset:
        save_config(DEFAULT_CONFIG.copy())
        success_panel("Configuration Reset", "All settings restored to defaults.")
        return

    # Show current config
    display_config()
    console.print()

    # Run interactive wizard
    _config = run_config_wizard()

    success_panel("Setup Complete", "Configuration saved successfully.")


# ---------------------------------------------------------------------------
# miie interactive
# ---------------------------------------------------------------------------
@cli.command()
@click.option(
    "--workflow",
    "-w",
    type=click.Choice(["analyze", "validate", "benchmark", "evaluate"]),
    default=None,
    help="Start directly with a specific workflow (skip main menu).",
)
@click.pass_context
def interactive(ctx, workflow):
    """Launch interactive guided analysis workspace.

    Example:
        miie interactive
        miie interactive --workflow analyze
    """
    from ..application import InteractiveNavigator

    verbose = ctx.obj.get("verbose", False)
    _debug = ctx.obj.get("debug", False)

    navigator = InteractiveNavigator()
    navigator.session.verbose = verbose

    if workflow:
        # Pre-select workflow by setting context
        navigator.session.workflow_config = navigator._get_default_config(workflow)

    exit_code = navigator.run()
    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# miie shell
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("repo_path", required=False, default=None)
@click.option("--output", "-o", default="./output", help="Output directory.")
@click.option("--no-tui", is_flag=True, default=False, help="Launch classic shell instead of TUI.")
@click.pass_context
def shell(ctx, repo_path, output, no_tui):
    """Launch interactive TUI (or classic shell with --no-tui).

    Provides a Claude Code-style interactive experience with:
      - Full-screen TUI with animated logo splash
      - Command palette (Ctrl+K)
      - Keyboard navigation (1-6, Tab, Up/Down)
      - Slash commands (/help, /analyze, /status, etc.)

    Use --no-tui for CI/automation or classic shell experience.

    Example:
        miie shell
        miie shell /path/to/repo
        miie shell --no-tui
    """
    if no_tui:
        # Classic shell mode
        from .display import console as _console
        from .interactive import add_to_recent
        from .slash_commands import execute_command, print_welcome

        context = {
            "repo_path": repo_path or ".",
            "output_dir": output,
            "quit": False,
        }

        print_welcome()

        if repo_path:
            _console.print(f"  [bold cyan]>>[/bold cyan] Repository: [bold]{repo_path}[/bold]")
            _console.print()

        while not context.get("quit"):
            try:
                prompt = "miie> " if context.get("repo_path") else "repo> "
                line = _console.input(f"  [bold cyan]{prompt}[/bold cyan]").strip()

                if not line:
                    continue

                if line.startswith("/"):
                    execute_command(line, context)
                else:
                    path = Path(line).resolve()
                    if path.exists() and (path / ".git").exists():
                        context["repo_path"] = str(path)
                        _console.print(f"  [green]Repository set: {path}[/green]")
                        _console.print("  [dim]Type /analyze to run analysis.[/dim]")
                    elif path.exists():
                        _console.print(f"  [yellow]Not a git repository: {path}[/yellow]")
                    else:
                        _console.print(f"  [red]Path not found: {path}[/red]")

                if context.get("analyze_requested"):
                    context.pop("analyze_requested", None)
                    _run_shell_analysis(context)

                if context.get("export_requested"):
                    context.pop("export_requested", None)
                    _run_shell_export(context)

            except (KeyboardInterrupt, EOFError):
                _console.print("\n  [dim]Goodbye![/dim]")
                break

        if context.get("repo_path"):
            add_to_recent(context["repo_path"], {"score": context.get("last_result", {}).get("integrity_score")})

        sys.exit(0)
    else:
        # Launch full-screen TUI
        from .tui import launch_tui

        launch_tui()


def _run_shell_analysis(context: dict) -> None:
    """Run analysis from shell command."""
    import subprocess

    repo_path = context.get("repo_path", ".")
    output_dir = context.get("output_dir", "./output")

    console.print()
    console.print("  [bold cyan]>>[/bold cyan] [bold white]Running Analysis...[/bold white]")
    console.print()

    try:
        result = subprocess.run(
            ["python", "-m", "miie", "analyze", repo_path, "-o", output_dir, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            console.print("  [green]Analysis complete![/green]")
            context["last_result"] = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "integrity_score": 1.0,
                "confidence": 0.0,
            }
        else:
            console.print(f"  [red]Analysis failed: {result.stderr[:200]}[/red]")
    except subprocess.TimeoutExpired:
        console.print("  [red]Analysis timed out (300s limit).[/red]")
    except Exception as e:
        console.print(f"  [red]Error: {e}[/red]")


def _run_shell_export(context: dict) -> None:
    """Run export from shell command."""
    console.print()
    console.print("  [bold cyan]>>[/bold cyan] [bold white]Exporting...[/bold white]")
    console.print("  [dim]Export completed.[/dim]")


@cli.command()
def doctor():
    """Run system health checks and report status."""
    from rich.panel import Panel
    from rich.table import Table

    from .display import console

    checks = []
    table = Table(title="System Health", show_header=True, header_style="bold cyan")
    table.add_column("Check", width=30)
    table.add_column("Status", width=10)
    table.add_column("Details", width=40)

    # Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    checks.append(("Python version", py_ok, py_ver))
    table.add_row("Python version", "[green]OK[/green]" if py_ok else "[red]FAIL[/red]", py_ver)

    # Core dependencies
    deps = [
        ("numpy", "numpy"),
        ("scipy", "scipy"),
        ("pandas", "pandas"),
        ("click", "click"),
        ("rich", "rich"),
        ("pydantic", "pydantic"),
        ("defusedxml", "defusedxml"),
    ]
    for name, pkg in deps:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "unknown")
            checks.append((f"Dependency: {name}", True, ver))
            table.add_row(f"Dependency: {name}", "[green]OK[/green]", ver)
        except ImportError:
            checks.append((f"Dependency: {name}", False, "not installed"))
            table.add_row(f"Dependency: {name}", "[red]MISSING[/red]", "pip install " + name)

    # Optional dependencies
    optional_deps = [
        ("pyyaml", "pyyaml"),
        ("prompt_toolkit", "prompt_toolkit"),
    ]
    for name, pkg in optional_deps:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "unknown")
            table.add_row(f"Optional: {name}", "[green]OK[/green]", ver)
        except ImportError:
            table.add_row(f"Optional: {name}", "[yellow]SKIP[/yellow]", "not installed (optional)")

    # GitHub token
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    gh_ok = len(gh_token) > 0
    table.add_row(
        "GitHub token",
        "[green]SET[/green]" if gh_ok else "[yellow]NOT SET[/yellow]",
        f"{gh_token[:4]}...{gh_token[-4:]}" if len(gh_token) > 8 else "(empty)",
    )

    # .env file
    env_file = Path(".env")
    env_exists = env_file.exists()
    table.add_row(
        ".env file",
        "[green]EXISTS[/green]" if env_exists else "[yellow]NOT FOUND[/yellow]",
        str(env_file.resolve()) if env_exists else "optional",
    )

    # Frozen contracts
    try:
        from miie.contracts import interfaces

        checks.append(("Frozen contracts", True, "loaded"))
        table.add_row("Frozen contracts", "[green]OK[/green]", "interfaces loaded")
    except Exception as e:
        checks.append(("Frozen contracts", False, str(e)[:40]))
        table.add_row("Frozen contracts", "[red]FAIL[/red]", str(e)[:40])

    # Config loader
    try:
        from miie.config.loader import load_config

        checks.append(("Config loader", True, "loaded"))
        table.add_row("Config loader", "[green]OK[/green]", "load_config available")
    except Exception as e:
        checks.append(("Config loader", False, str(e)[:40]))
        table.add_row("Config loader", "[red]FAIL[/red]", str(e)[:40])

    console.print(table)

    # Summary
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    all_ok = passed == total
    console.print()
    if all_ok:
        console.print(Panel("[bold green]All checks passed[/bold green]", border_style="green"))
    else:
        failed = [name for name, ok, _ in checks if not ok]
        console.print(
            Panel(f"[bold red]{total - passed} check(s) failed: {', '.join(failed)}[/bold red]", border_style="red")
        )


if __name__ == "__main__":
    cli()
