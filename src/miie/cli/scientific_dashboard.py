"""Scientific Dashboard for MIIE CLI.

Renders metric cards, confidence factor breakdown, and detector
status in a high-density format inspired by btop and K9s.

Design principles:
- btop: Dense metric display with color-coded values
- K9s: Minimal decoration, maximum signal density
- Evidence-first: Every number backed by statistical context

The scientific engine is frozen. This module handles UX only.
"""

from __future__ import annotations

from typing import Any

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .design_tokens import TOKENS
from .display import console
from .responsive import get_layout
from .semantic_colors import (
    BORDER_ERROR,
    BORDER_SUCCESS,
    BORDER_WARNING,
    CAUTION,
    HEALTHY,
    RISK,
    STABLE,
    score_bar,
    score_bar_labeled,
    score_to_color,
    score_to_label,
    source_to_label,
)

# ── Metric Card Renderer ─────────────────────────────────────────────


def render_metric_card(
    metric_id: str,
    values: list[float] | None = None,
    source: str = "git",
    purpose: str = "",
    compact: bool = False,
) -> Panel:
    """Render a single metric as a compact card.

    Shows: metric name, source, current value, trend indicator.
    """
    layout = get_layout()
    source_label = source_to_label(source)

    # Calculate trend from values
    trend_icon = ""
    trend_color = "dim"
    if values and len(values) >= 2:
        last = values[-1]
        prev = values[-2]
        if last > prev * 1.1:
            trend_icon = "^"
            trend_color = "yellow"
        elif last < prev * 0.9:
            trend_icon = "v"
            trend_color = "green"
        else:
            trend_icon = "="
            trend_color = "dim"

    # Build card content
    content = Text()
    content.append(f"{metric_id}", style="bold cyan")
    content.append(f"  {source_label}", style="dim")

    if not compact and purpose:
        content.append(f"\n{purpose}", style="dim")

    if values:
        last_val = values[-1]
        val_color = score_to_color(last_val)
        content.append(f"\n{last_val:.3f}", style=f"bold {val_color}")
        if trend_icon:
            content.append(f" {trend_icon}", style=trend_color)
        if len(values) >= 2:
            delta = values[-1] - values[-2]
            content.append(f" ({delta:+.3f})", style="dim")

    title = f"[bold]{metric_id}[/bold] [{source_label}]"
    return Panel(
        content,
        title=title,
        border_style="dim white",
        expand=True,
    )


# ── Confidence Factor Breakdown ───────────────────────────────────────

CONFIDENCE_FACTOR_INFO = {
    "beta_1": ("Data Completeness", "Fraction of observations with non-null values"),
    "beta_2": ("Statistical Power", "Effective sample size relative to minimum"),
    "beta_3": ("Missing Data", "Penalty for aggregate metrics with missing windows"),
    "beta_4": ("Methodological", "Based on data source quality (git > proxy > github)"),
    "beta_5": ("Temporal Coverage", "Time span of data relative to window count"),
    "beta_6": ("Cross-Validation", "Stability across windowing strategies"),
}


def render_confidence_breakdown(
    confidence_factors: dict[str, float] | None = None,
    confidence_overall: float = 0.0,
) -> Panel:
    """Render confidence score with factor breakdown.

    Shows each factor as a bar with explanation.
    """
    table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1), expand=True)
    table.add_column("Factor", style="bold", width=10)
    table.add_column("Name", width=18)
    table.add_column("Score", width=8)
    if get_layout().show_detail:
        table.add_column("Bar", min_width=12)
        table.add_column("Description", style="dim", ratio=1)

    if confidence_factors:
        for factor_id in ["beta_1", "beta_2", "beta_3", "beta_4", "beta_5", "beta_6"]:
            value = confidence_factors.get(factor_id, 0.0)
            if isinstance(value, dict):
                value = value.get("value", 0.0)
            name, desc = CONFIDENCE_FACTOR_INFO.get(factor_id, (factor_id, ""))
            color = score_to_color(value)

            if get_layout().show_detail:
                table.add_row(
                    factor_id,
                    name,
                    f"[{color}]{value:.3f}[/{color}]",
                    score_bar(value, 8),
                    desc,
                )
            else:
                table.add_row(
                    factor_id,
                    name,
                    f"[{color}]{value:.3f}[/{color}]",
                )

    # Overall row
    overall_color = score_to_color(confidence_overall)
    if get_layout().show_detail:
        table.add_section()
        table.add_row(
            "OVERALL",
            "Confidence",
            f"[bold {overall_color}]{confidence_overall:.3f}[/bold {overall_color}]",
            score_bar_labeled(confidence_overall, 8),
            score_to_label(confidence_overall),
        )
    else:
        table.add_section()
        table.add_row(
            "OVERALL",
            "Confidence",
            f"[bold {overall_color}]{confidence_overall:.3f}[/bold {overall_color}]",
        )

    return Panel(
        table,
        title="[bold cyan]Confidence Factors[/bold cyan]",
        border_style="dim white",
        padding=(0, 1),
    )


# ── Detector Detail Cards ─────────────────────────────────────────────

DETECTOR_INFO = {
    "D-01": {
        "name": "Distributional Drift",
        "description": "Kolmogorov-Smirnov test + PSI across windows",
        "metrics": ["M-01", "M-02", "M-03", "M-06"],
    },
    "D-02": {
        "name": "Correlation Breakdown",
        "description": "Pearson/Spearman correlation stability",
        "metrics": ["M-01", "M-02", "M-03", "M-04", "M-05", "M-06", "M-07"],
    },
    "D-03": {
        "name": "Threshold Compression",
        "description": "Hartigan dip test for bimodality",
        "metrics": ["M-01", "M-04", "M-05"],
    },
}


def render_detector_detail(
    det_id: str,
    det_data: dict[str, Any],
    compact: bool = False,
) -> Panel:
    """Render a single detector's results as a detail card."""
    info = DETECTOR_INFO.get(det_id, {"name": det_id, "description": "", "metrics": []})

    # Determine status
    triggered = False
    if isinstance(det_data, dict) and det_data.get("status") not in ("error", "skipped"):
        triggered = (
            det_data.get("drift_detected")
            or det_data.get("breakdown_detected")
            or det_data.get("compression_detected", False)
        )

    status_color = RISK if triggered else HEALTHY
    status_icon = "X" if triggered else "V"
    status_text = "TRIGGERED" if triggered else "CLEAR"

    content = Text()
    content.append(f"{status_icon} {status_text}", style=f"bold {status_color}")

    if not compact:
        content.append(f"\n{info['description']}", style="dim")

        # Key statistics
        if isinstance(det_data, dict):
            if "psi_value" in det_data:
                content.append(f"\nPSI: {det_data['psi_value']:.4f}", style="bold")
            if "dip_statistic" in det_data:
                content.append(f"\nDip: {det_data['dip_statistic']:.4f}", style="bold")
            if "pearson_r" in det_data:
                content.append(f"\nPearson r: {det_data['pearson_r']:.4f}", style="bold")
            if "p_value" in det_data:
                p = det_data["p_value"]
                content.append(f"\np-value: {p:.4f}", style="dim")
                if p < 0.05:
                    content.append(" (significant)", style="yellow")

    return Panel(
        content,
        title=f"[bold]{det_id}[/bold] {info['name']}",
        border_style=status_color,
        padding=(0, 1),
        expand=True,
    )


# ── Full Dashboard Renderer ───────────────────────────────────────────


def render_scientific_dashboard(
    integrity_score: float,
    confidence_score: float,
    confidence_factors: dict[str, Any] | None,
    detector_outputs: dict[str, Any],
    metric_sources: dict[str, str],
    compact: bool = False,
) -> Group:
    """Render the full scientific dashboard.

    Assembles metric cards, confidence breakdown, and detector details.
    """
    layout = get_layout()
    content_parts = []

    # ── Confidence Section ──
    if confidence_factors:
        conf_panel = render_confidence_breakdown(confidence_factors, confidence_score)
        content_parts.append(conf_panel)

    # ── Detector Section ──
    det_panels = []
    for det_id in sorted(detector_outputs.keys()):
        det_data = detector_outputs[det_id]
        if not isinstance(det_data, dict):
            det_data = {"status": "error"}
        panel = render_detector_detail(det_id, det_data, compact=compact)
        det_panels.append(panel)

    if det_panels:
        if layout.columns >= 90:
            # Side by side
            content_parts.append(Columns(det_panels, equal=True, expand=True))
        else:
            # Stacked
            for p in det_panels:
                content_parts.append(p)

    if not content_parts:
        return Group(Text("  No data available", style="dim"))

    return Group(*content_parts)
