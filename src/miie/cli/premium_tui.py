"""Premium TUI for MIIE CLI -- Flagship Terminal Experience.

Flagship-level output with:
- Evidence-based semantic colors (every color maps to scientific meaning)
- Adaptive responsive layout (adapts to terminal width)
- Permanent brand identity (flagship header)
- Information hierarchy (3-second rule: most important info first)
- Keyboard-driven interaction patterns

Design principles derived from:
- LazyGit: Dense information hierarchy, status-driven colors
- K9s: Minimal decoration, maximum signal
- btop: High-density metric display
- gh CLI: Consistent spacing, clear section boundaries

The scientific engine is frozen. This module handles UX only.
"""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .design_tokens import TOKENS
from .display import MIIE_THEME, console
from .responsive import get_layout, get_terminal_width
from .semantic_colors import (
    ACTION_MESSAGES,
    BORDER_ERROR,
    BORDER_SUCCESS,
    BORDER_WARNING,
    CAUTION,
    DETECTOR_CLEAR,
    DETECTOR_ERROR,
    DETECTOR_SKIPPED,
    DETECTOR_TRIGGERED,
    DETECTOR_VERDICTS_CLEAR,
    DETECTOR_VERDICTS_TRIGGERED,
    HEALTHY,
    RISK,
    SOURCE_GIT,
    SOURCE_GITHUB,
    SOURCE_PROXY,
    STABLE,
    VERDICT_MESSAGES,
    score_bar,
    score_bar_labeled,
    score_to_color,
    score_to_label,
    source_to_label,
    stage_status_color,
    stage_status_icon,
    verdict_color,
    verdict_icon,
)

# ── Visual Constants (from design tokens) ──────────────────────────────

_BORDER_PRIMARY = "bright_cyan"
_BORDER_SUCCESS_V = BORDER_SUCCESS
_BORDER_WARNING_V = BORDER_WARNING
_BORDER_ERROR_V = BORDER_ERROR
_BORDER_NEUTRAL = "dim white"

_STATUS_ICONS = {
    "pending": "[dim]o[/dim]",
    "running": "[bold cyan]*[/bold cyan]",
    "done": "[bold green]V[/bold green]",
    "error": "[bold red]X[/bold red]",
    "skip": "[dim]-[/dim]",
}

_DETECTOR_ICONS = {
    "CLEAR": "[bold green]V CLEAR[/bold green]",
    "DETECTED": "[bold red]X DETECTED[/bold red]",
    "ERROR": "[bold yellow]! ERROR[/bold yellow]",
    "SKIPPED": "[dim]- SKIPPED[/dim]",
}


# ── Score Display ──────────────────────────────────────────────────────


def _score_color(score: float, thresholds: tuple = (0.9, 0.7, 0.5)) -> str:
    """Return Rich style based on score value (delegates to semantic colors)."""
    return score_to_color(score)


def _score_bar(score: float, width: int = 20) -> str:
    """Create a visual score bar (delegates to semantic colors)."""
    return score_bar(score, width)


def _format_time(seconds: float) -> str:
    """Format seconds into human-readable time."""
    return TOKENS.format_time(seconds)


# ── Premium Pipeline Progress ─────────────────────────────────────────


class PremiumPipelineProgress:
    """Real-time pipeline progress with Rich Live display.

    Adapts to terminal width via responsive layout engine.
    Uses semantic colors from the design token system.
    """

    STAGES = [
        ("acquisition", "Repository Acquisition", "Cloning / loading repo"),
        ("validation", "Repository Validation", "Checking metadata"),
        ("extraction", "Metric Extraction", "Pulling metrics"),
        ("segmentation", "Window Generation", "Building windows"),
        ("detection", "Detector Execution", "Running detectors"),
        ("evidence", "Evidence Generation", "Generating evidence"),
        ("reporting", "Final Assessment", "Final assessment"),
    ]

    def __init__(self, total_stages: int = 7, verbose: bool = False) -> None:
        self.total_stages = total_stages
        self.verbose = verbose
        self._timings: dict[str, float] = {}
        self._stage_start: float = 0.0
        self._current_idx: int = -1
        self._stage_states: dict[str, str] = {}
        self._stage_details: dict[str, str] = {}
        self._live: Live | None = None
        self._repo_name: str = ""
        self._start_time: float = 0.0

    def start(self, repo_name: str = "") -> None:
        """Initialize the progress display."""
        self._start_time = time.perf_counter()
        self._repo_name = repo_name

    def stop(self) -> None:
        """Stop the progress display."""
        pass

    def _build_layout(self) -> Panel:
        """Build the live dashboard layout with adaptive width."""
        layout = get_layout()

        # Stage table
        stage_table = Table(
            show_header=True,
            header_style="bold cyan",
            box=None,
            padding=(0, 1),
            expand=True,
        )
        stage_table.add_column("Status", width=3, justify="center")
        stage_table.add_column("Stage", style="bold", min_width=14)
        if layout.show_detail:
            stage_table.add_column("Detail", style="dim", ratio=1)
        if layout.show_timing:
            stage_table.add_column("Time", justify="right", style="cyan", width=8)

        for i, (key, name, _) in enumerate(self.STAGES):
            state = self._stage_states.get(key, "pending")
            icon = stage_status_icon(state)
            detail = self._stage_details.get(key, "")

            # Truncate detail based on layout
            if layout.show_detail and len(detail) > layout.max_detail_length:
                detail = detail[: layout.max_detail_length - 3] + "..."

            timing = ""
            if key in self._timings:
                timing = _format_time(self._timings[key])
            elif state == "running":
                elapsed = time.perf_counter() - self._stage_start
                timing = f"{elapsed:.1f}s"

            # Highlight current stage using semantic colors
            color = stage_status_color(state)
            name_style = f"bold white" if state == "running" else ("bold green" if state == "done" else "")
            if name_style:
                name = f"[{name_style}]{name}[/{name_style}]"

            if layout.show_detail and layout.show_timing:
                stage_table.add_row(icon, name, detail, timing)
            elif layout.show_detail:
                stage_table.add_row(icon, name, detail)
            else:
                stage_table.add_row(icon, name)

        # Progress bar
        completed = sum(1 for s in self._stage_states.values() if s == "done")
        total = len(self.STAGES)
        progress_text = Text()
        progress_text.append(f"  [{completed}/{total}] ", style="bold cyan")
        elapsed = time.perf_counter() - self._start_time
        progress_text.append(_format_time(elapsed), style="dim")

        # Build content
        content = Group(stage_table, progress_text)

        return Panel(
            content,
            title=f"[bold cyan]MIIE Pipeline[/bold cyan] [dim]{self._repo_name}[/dim]",
            border_style=_BORDER_PRIMARY,
            padding=(0, 1),
        )

    def _refresh(self) -> None:
        """Refresh the live display."""
        if self._live:
            self._live.update(self._build_layout())

    def stage_start(self, stage_key: str, detail: str = "") -> None:
        """Mark start of a pipeline stage."""
        self._current_idx += 1
        self._stage_start = time.perf_counter()
        self._stage_states[stage_key] = "running"
        self._stage_details[stage_key] = detail
        # Print directly for test capture
        _stage_map = {k: (n, d) for k, n, d in self.STAGES}
        name = _stage_map.get(stage_key, (stage_key, ""))[0]
        stage_num = self._current_idx + 1
        console.print(f"  [cyan]{stage_num}/{self.total_stages}[/cyan] " f"[bold]{name}[/bold] {detail}")
        self._refresh()

    def stage_complete(self, stage_key: str, detail: str = "") -> None:
        """Mark completion of a pipeline stage."""
        elapsed = time.perf_counter() - self._stage_start
        self._timings[stage_key] = elapsed
        self._stage_states[stage_key] = "done"
        self._stage_details[stage_key] = detail
        _stage_map = {k: (n, d) for k, n, d in self.STAGES}
        name = _stage_map.get(stage_key, (stage_key, ""))[0]
        stage_num = self._current_idx + 1
        console.print(
            f"  [green]V {stage_num}/{self.total_stages}[/green] "
            f"[bold]{name}[/bold] [dim]{detail}[/dim] [cyan]{_format_time(elapsed)}[/cyan]"
        )
        self._refresh()

    def stage_error(self, stage_key: str, error: str = "") -> None:
        """Mark a pipeline stage as failed."""
        elapsed = time.perf_counter() - self._stage_start
        self._timings[stage_key] = elapsed
        self._stage_states[stage_key] = "error"
        self._stage_details[stage_key] = error
        self._refresh()

    def action(self, message: str) -> None:
        """Update action message for current stage."""
        if self._current_idx >= 0:
            key = self.STAGES[self._current_idx][0]
            self._stage_details[key] = message
            self._refresh()

    @property
    def timings(self) -> dict[str, float]:
        return self._timings.copy()

    @property
    def total_time(self) -> float:
        return sum(self._timings.values())


# ── Executive Summary Panel ───────────────────────────────────────────


def display_executive_summary(
    integrity_score: float,
    confidence_score: float,
    total_commits: Any,
    contributor_count: Any,
    window_count: int,
    detector_outputs: dict[str, Any],
    timings: dict[str, float] | None = None,
    repo_name: str = "",
    verbose: bool = False,
    confidence_band: str = "low",
    confidence_factors: dict[str, float] | None = None,
) -> None:
    """Display the premium executive summary panel.

    Uses adaptive layout based on terminal width.
    Colors derived from semantic color system.

    Now includes prominent confidence band display (war room fix).
    """
    layout = get_layout()

    # === Confidence Band (shown FIRST per war room finding) ===
    band_styles = {
        "high": ("bold green", "HIGH"),
        "medium": ("bold yellow", "MEDIUM"),
        "low": ("bold red", "LOW"),
    }
    band_style, band_text = band_styles.get(confidence_band, ("bold red", "LOW"))

    # Confidence bottleneck factor
    bottleneck_text = ""
    if confidence_factors:
        factor_names = {
            "sample_size": "Sample size",
            "variance": "Variance",
            "missing_data": "Missing data",
            "window_balance": "Window balance",
            "detector_success": "Detector success",
            "observation_quality": "Observation quality",
        }
        min_key = min(confidence_factors, key=confidence_factors.get)
        min_val = confidence_factors[min_key]
        min_name = factor_names.get(min_key, min_key)
        bottleneck_text = f"Bottleneck: {min_name}={min_val:.3f}"

    # Repository info table
    repo_table = Table(show_header=False, box=None, padding=(0, 2))
    repo_table.add_column("Key", style="dim", min_width=14)
    repo_table.add_column("Value", style="bold")
    repo_table.add_row("Repository", repo_name or "Local")
    repo_table.add_row("Commits", str(total_commits))
    repo_table.add_row("Contributors", str(contributor_count))
    repo_table.add_row("Windows", str(window_count))

    # Score display using semantic colors
    integrity_color = score_to_color(integrity_score)
    confidence_color = score_to_color(confidence_score)

    scores_table = Table(show_header=False, box=None, padding=(0, 2))
    scores_table.add_column("Metric", style="bold", min_width=14)
    scores_table.add_column("Score", min_width=8)
    if layout.show_detail:
        scores_table.add_column("Bar", min_width=layout.score_bar_width + 6)
    scores_table.add_row(
        "Integrity",
        f"[{integrity_color}]{integrity_score:.3f}[/{integrity_color}]",
        score_bar_labeled(integrity_score, layout.score_bar_width) if layout.show_detail else "",
    )
    scores_table.add_row(
        "Confidence",
        f"[{confidence_color}]{confidence_score:.3f}[/{confidence_color}]",
        score_bar_labeled(confidence_score, layout.score_bar_width) if layout.show_detail else "",
    )

    # Assessment labels using semantic system
    integrity_label = score_to_label(integrity_score)
    confidence_label = score_to_label(confidence_score)

    # Detector summary
    det_table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    det_table.add_column("Detector", style="bold", min_width=8)
    det_table.add_column("Status", min_width=14)
    if layout.show_detail:
        det_table.add_column("Detail", style="dim", ratio=1)

    _det_names = {
        "D-01": "Drift",
        "D-02": "Correlation",
        "D-03": "Compression",
    }

    for det_id, det_data in sorted(detector_outputs.items()):
        name = _det_names.get(det_id, det_id)
        if not isinstance(det_data, dict):
            status = _DETECTOR_ICONS["ERROR"]
            detail = "Invalid output"
        elif det_data.get("status") in ("error", "skipped"):
            status = _DETECTOR_ICONS["SKIPPED"]
            detail = det_data.get("reason", "unknown")[: layout.max_detail_length]
        else:
            triggered = (
                det_data.get("drift_detected")
                or det_data.get("breakdown_detected")
                or det_data.get("compression_detected", False)
            )
            status = _DETECTOR_ICONS["DETECTED"] if triggered else _DETECTOR_ICONS["CLEAR"]
            detail = ""
            if not triggered:
                detail = f"OK [{det_id}]"
            elif "psi_value" in det_data:
                detail = f"PSI={det_data['psi_value']:.3f}"
            elif "pearson_r" in det_data:
                detail = f"r={det_data['pearson_r']:.3f}"
            elif "dip_statistic" in det_data:
                detail = f"dip={det_data['dip_statistic']:.3f}"

        if layout.show_detail:
            det_table.add_row(name, status, detail)
        else:
            det_table.add_row(name, status)

    # Timing summary
    timing_text = ""
    if timings and layout.show_timing:
        timing_parts = []
        for key, elapsed in timings.items():
            stage_name = {
                "acquisition": "acq",
                "validation": "val",
                "extraction": "ext",
                "segmentation": "seg",
                "detection": "det",
                "evidence": "evi",
                "reporting": "rpt",
            }.get(key, key[:3])
            timing_parts.append(f"{stage_name}={_format_time(elapsed)}")
        timing_text = "  ".join(timing_parts)

    # Build final panel content — confidence band first
    content = Group(
        Text(),
        Text(f"  Confidence Band: [{band_style}]{band_text}[/{band_style}]", style="bold"),
    )

    if bottleneck_text:
        content = Group(content, Text(f"  {bottleneck_text}", style="dim"))

    content = Group(
        content,
        Text(),
        Text("  Analysis Coverage", style="bold cyan"),
        Text("  " + "-" * 48, style="dim"),
        repo_table,
        Text(),
        Text("  Scores", style="bold cyan"),
        Text("  " + "-" * 48, style="dim"),
        scores_table,
        Text(f"  Integrity: {integrity_label}  |  Confidence: {confidence_label}", style="dim"),
        Text(),
        Text("  Integrity Findings", style="bold cyan"),
        Text("  " + "-" * 48, style="dim"),
        det_table,
    )

    if timing_text:
        content = Group(
            content,
            Text(),
            Text(f"  Timing: {timing_text}", style="dim"),
            Text(f"  Total: {_format_time(sum(timings.values()))}", style="bold"),
        )

    # Overall verdict using semantic colors
    triggered_count = sum(
        1
        for d in detector_outputs.values()
        if isinstance(d, dict)
        and (d.get("drift_detected") or d.get("breakdown_detected") or d.get("compression_detected", False))
    )

    v_color, border = verdict_color(integrity_score, confidence_score, triggered_count)
    v_icon = verdict_icon(integrity_score, confidence_score, triggered_count)

    if integrity_score >= 1.0 and confidence_score >= 0.5 and triggered_count == 0:
        verdict = f"{v_icon} [bold green]INTEGRITY VERIFIED[/bold green]"
    elif triggered_count > 0:
        verdict = f"{v_icon} [bold red]{triggered_count} DETECTOR(S) TRIGGERED[/bold red]"
    elif confidence_band == "low":
        verdict = f"{v_icon} [bold yellow]INTEGRITY UNKNOWN (LOW CONFIDENCE)[/bold yellow]"
    else:
        verdict = f"{v_icon} [bold yellow]PARTIAL INTEGRITY[/bold yellow]"

    content = Group(
        content,
        Text(),
        Text("  Metric Integrity Verdict", style="bold cyan"),
        Text("  " + "-" * 48, style="dim"),
    )

    # Human-friendly verdict message (hidden in verbose mode)
    if not verbose:
        if confidence_band == "low":
            verdict_msg = "Insufficient data for reliable verdict. Results may be misleading."
        elif triggered_count == 0 and integrity_score >= 0.9:
            verdict_msg = VERDICT_MESSAGES["healthy"]
        elif triggered_count == 0 and integrity_score >= 0.7:
            verdict_msg = VERDICT_MESSAGES["stable"]
        elif triggered_count == 1:
            verdict_msg = VERDICT_MESSAGES["partial"]
        else:
            verdict_msg = VERDICT_MESSAGES["critical"]

        content = Group(
            content,
            Text(f"  {verdict_msg}", style="bold"),
        )

        # Per-detector verdict lines
        for det_id in sorted(detector_outputs.keys()):
            det_data = detector_outputs[det_id]
            if not isinstance(det_data, dict):
                triggered = False
            elif det_data.get("status") in ("error", "skipped"):
                continue
            else:
                triggered = (
                    det_data.get("drift_detected")
                    or det_data.get("breakdown_detected")
                    or det_data.get("compression_detected", False)
                )
            if triggered:
                msg = DETECTOR_VERDICTS_TRIGGERED.get(det_id, det_id)
                content = Group(content, Text(f"  {msg}", style="yellow"))
            else:
                msg = DETECTOR_VERDICTS_CLEAR.get(det_id, det_id)
                content = Group(content, Text(f"  {msg}", style="green"))

    content = Group(
        content,
        Text(),
        Text(f"  {verdict}", style="bold"),
        Text(),
        Text("  Recommended Action", style="bold cyan"),
        Text("  " + "-" * 48, style="dim"),
    )

    if confidence_band == "low":
        action_msg = "Increase analysis window or use --max-commits for more data."
    elif triggered_count == 0 and integrity_score >= 0.9:
        action_msg = ACTION_MESSAGES["no_action"]
    elif triggered_count == 0 and integrity_score >= 0.7:
        action_msg = ACTION_MESSAGES["monitor"]
    elif triggered_count == 1:
        action_msg = ACTION_MESSAGES["review"]
    else:
        action_msg = ACTION_MESSAGES["investigate"]

    content = Group(content, Text(f"  {action_msg}", style="bold"))

    console.print()
    console.print(
        Panel(
            content,
            title="[bold cyan]Analysis Results[/bold cyan]",
            border_style=border,
            padding=(0, 1),
        )
    )


# ── Metric Source Indicator ───────────────────────────────────────────

METRIC_SOURCES = {
    "M-01": "git",
    "M-02": "git",
    "M-03": "git",
    "M-04": "proxy",
    "M-05": "github",
    "M-06": "git",
    "M-07": "git",
}

METRIC_PURPOSES = {
    "M-01": "Specification entropy",
    "M-02": "Commit frequency",
    "M-03": "Code churn ratio",
    "M-04": "Test coverage",
    "M-05": "PR review latency",
    "M-06": "File activity breadth",
    "M-07": "Branch recency",
}


def display_metric_sources(metric_names: list[str]) -> None:
    """Display metric source indicators with semantic colors."""
    table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    table.add_column("Metric", style="bold", width=6)
    table.add_column("Source", width=8)
    table.add_column("Purpose", style="dim", ratio=1)

    for metric_id in metric_names:
        source = METRIC_SOURCES.get(metric_id, "unknown")
        source_label = source_to_label(source)
        purpose = METRIC_PURPOSES.get(metric_id, "")
        table.add_row(metric_id, source_label, purpose)

    console.print()
    console.print("  [bold cyan]Metric Sources[/bold cyan]")
    console.print(table)


# ── Premium Footer ────────────────────────────────────────────────────


def display_premium_footer(
    total_time: float,
    report_paths: dict[str, str] | None = None,
    success: bool = True,
) -> None:
    """Display premium analysis complete footer."""
    border = BORDER_SUCCESS if success else BORDER_ERROR
    icon = "[bold green]V[/bold green]" if success else "[bold red]X[/bold red]"

    content = Text()
    content.append(f"\n  {icon}  ", style="bold")
    content.append("Analysis Complete  ", style="bold")
    content.append(f"({_format_time(total_time)})", style="dim")

    if report_paths:
        content.append("\n\n")
        content.append("  Reports Saved\n", style="bold cyan")
        for fmt, path in report_paths.items():
            content.append(f"    {fmt}: ", style="dim")
            content.append(f"{path}\n", style="bold")

    content.append("\n")

    console.print(
        Panel(
            content,
            border_style=border,
            padding=(0, 2),
            expand=False,
        )
    )


# ── Compatibility Wrapper ─────────────────────────────────────────────


def create_pipeline_progress(verbose: bool = False) -> PremiumPipelineProgress:
    """Create a premium pipeline progress instance."""
    return PremiumPipelineProgress(verbose=verbose)
