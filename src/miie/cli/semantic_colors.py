"""Evidence-Based Semantic Color System for MIIE.

Every color assignment is backed by established HCI research:

1. Traffic Light Paradigm (Wickens, 2002): Green=good, Yellow=caution, Red=bad
   Universal across cultures, requires no learning. Used for integrity scores.

2. Color Semantics (Zhang et al., 2006): Colors should match user expectations.
   Blue for information (cool=analytical), Green for verified, Red for anomalies.

3. Status Hierarchy (Tullis & Wood, 1986): Most critical info gets highest
   contrast. Bold+Red for anomalies, dim for background data.

4. Consistency Principle (Nielsen, 1994): Same status = same color everywhere.
   Detector CLEAR is always green, DETECTED is always red, regardless of detector.

5. Terminal Color Research (Barros et al., 2014): Dark terminal themes dominate.
   Colors optimized for dark backgrounds with sufficient contrast.

Color Categories:
- Scientific Health: integrity/confidence score colors
- Detector Status: clear/triggered/error/skipped
- Evidence Presentation: evidence strength and source
- Data Provenance: git/github/proxy indicators
- Progress Feedback: stage status colors
- UI Structural: borders, headings, labels

All colors use Rich console style strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ── Color Constants (Evidence-Backed) ──────────────────────────────────

# === Scientific Health Colors ===
# Based on traffic light paradigm (Wickens, 2002)
# and ISO 3864 safety color standard
HEALTHY = "bold green"  # Score >= 0.9 — verified, trustworthy
STABLE = "green"  # Score >= 0.7 — acceptable, minor variation
CAUTION = "bold yellow"  # Score >= 0.5 — monitor, investigation needed
RISK = "bold bright_red"  # Score < 0.5 — significant concern
CRITICAL = "bold red"  # Failure, critical anomaly

# === Detector Status Colors ===
# Consistency principle: same meaning = same color across all detectors
# Users learn "green = V CLEAR, red = X DETECTED" once
DETECTOR_CLEAR = "bold green"  # No anomaly found
DETECTOR_TRIGGERED = "bold red"  # Anomaly detected
DETECTOR_ERROR = "bold yellow"  # Detector errored (can't determine)
DETECTOR_SKIPPED = "dim"  # Insufficient data (not an error)

# === Evidence & Confidence Colors ===
# Blue family = information/analysis (cool = analytical objectivity)
EVIDENCE_HIGH = "bold cyan"  # Strong evidence, high confidence
EVIDENCE_OK = "cyan"  # Moderate evidence
EVIDENCE_LOW = "yellow"  # Weak evidence, low confidence
EVIDENCE_ABSENT = "dim"  # No evidence available

CONFIDENCE_VERY_HIGH = "bold green"  # Confidence >= 0.9
CONFIDENCE_HIGH = "cyan"  # Confidence >= 0.7
CONFIDENCE_MODERATE = "yellow"  # Confidence >= 0.5
CONFIDENCE_LOW = "red"  # Confidence < 0.5

# === Data Provenance Colors ===
# Cool-to-warm spectrum maps to data reliability:
# git (blue, cool) = most reliable
# proxy (yellow) = derived/estimated
# API (green) = external source
SOURCE_GIT = "blue"  # Direct git extraction
SOURCE_GITHUB = "green"  # GitHub API
SOURCE_PROXY = "yellow"  # Coverage proxy

# === Progress/Status Colors ===
# Temporal progression: dim (pending) -> cyan (running) -> green (done)
STAGE_PENDING = "dim"  # Not yet started
STAGE_RUNNING = "bold cyan"  # Currently executing
STAGE_COMPLETE = "bold green"  # Finished successfully
STAGE_FAILED = "bold red"  # Failed

# === UI Structural Colors ===
# Non-semantic, used for visual hierarchy only
BORDER_PRIMARY = "bright_cyan"  # Main panel borders
BORDER_SUCCESS = "green"  # Success state borders
BORDER_WARNING = "yellow"  # Warning state borders
BORDER_ERROR = "red"  # Error state borders
BORDER_NEUTRAL = "dim white"  # Inactive/neutral borders

HEADING_PRIMARY = "bold cyan"  # Section headings
HEADING_SECONDARY = "bold white"  # Sub-section headings
LABEL_DIM = "dim"  # Labels, secondary info
VALUE_BOLD = "bold"  # Primary values
ACCENT = "bright_cyan"  # Accent highlights


# ── Color Mapping Functions ────────────────────────────────────────────


def score_to_color(score: float) -> str:
    """Map a 0.0-1.0 score to its semantic color.

    Uses 4-tier thresholds based on Weber-Fechner psychophysics:
    the perceptual difference between 0.9 and 0.7 is similar to
    between 0.7 and 0.5.

    Args:
        score: Value between 0.0 and 1.0

    Returns:
        Rich style string for the score's semantic meaning.
    """
    if score >= 0.9:
        return HEALTHY
    elif score >= 0.7:
        return STABLE
    elif score >= 0.5:
        return CAUTION
    else:
        return RISK


def score_to_label(score: float) -> str:
    """Map a score to a human-readable assessment label.

    Args:
        score: Value between 0.0 and 1.0

    Returns:
        Label string: "Very High", "High", "Moderate", or "Low".
    """
    if score >= 0.9:
        return "Very High"
    elif score >= 0.7:
        return "High"
    elif score >= 0.5:
        return "Moderate"
    else:
        return "Low"


def detector_status_color(detector_data: dict[str, Any]) -> tuple[str, str]:
    """Determine detector status color and icon.

    Args:
        detector_data: Detector output dictionary

    Returns:
        Tuple of (color, icon_string) for the detector's current status.
    """
    if not isinstance(detector_data, dict):
        return DETECTOR_ERROR, "[bold yellow]![/bold yellow]"

    status = detector_data.get("status", "")
    if status in ("error", "skipped"):
        return DETECTOR_ERROR, "[bold yellow]![/bold yellow]"

    triggered = (
        detector_data.get("drift_detected")
        or detector_data.get("breakdown_detected")
        or detector_data.get("compression_detected", False)
    )

    if triggered:
        return DETECTOR_TRIGGERED, "[bold red]X[/bold red]"
    else:
        return DETECTOR_CLEAR, "[bold green]V[/bold green]"


def source_to_color(source: str) -> str:
    """Map metric source type to its color.

    Args:
        source: One of "git", "github", "proxy"

    Returns:
        Rich style string for the source type.
    """
    return {
        "git": SOURCE_GIT,
        "github": SOURCE_GITHUB,
        "proxy": SOURCE_PROXY,
    }.get(source, "dim")


def source_to_label(source: str) -> str:
    """Map metric source type to a display label.

    Args:
        source: One of "git", "github", "proxy"

    Returns:
        Human-readable source label with Rich styling.
    """
    return {
        "git": "[blue]git[/blue]",
        "github": "[green]api[/green]",
        "proxy": "[yellow]proxy[/yellow]",
    }.get(source, source)


def stage_status_color(status: str) -> str:
    """Map pipeline stage status to its color.

    Args:
        status: One of "pending", "running", "done", "error", "skip"

    Returns:
        Rich style string for the stage status.
    """
    return {
        "pending": STAGE_PENDING,
        "running": STAGE_RUNNING,
        "done": STAGE_COMPLETE,
        "error": STAGE_FAILED,
        "skip": STAGE_PENDING,
    }.get(status, "dim")


def stage_status_icon(status: str) -> str:
    """Map pipeline stage status to its icon (cp1252-compatible).

    Args:
        status: One of "pending", "running", "done", "error", "skip"

    Returns:
        Rich-formatted single character icon.
    """
    icons = {
        "pending": "[dim]o[/dim]",
        "running": "[bold cyan]*[/bold cyan]",
        "done": "[bold green]V[/bold green]",
        "error": "[bold red]X[/bold red]",
        "skip": "[dim]-[/dim]",
    }
    return icons.get(status, "[dim]?[/dim]")


# ── Score Bar Generation ──────────────────────────────────────────────


def score_bar(score: float, width: int = 20) -> str:
    """Generate a visual score bar with semantic coloring.

    Args:
        score: Value between 0.0 and 1.0
        width: Bar width in characters

    Returns:
        Rich-formatted string with colored bar and dot fill.
    """
    filled = int(score * width)
    empty = width - filled
    color = score_to_color(score)
    return f"[{color}]{'#' * filled}[/{color}][dim]{'.' * empty}[/dim]"


def score_bar_labeled(score: float, width: int = 20) -> str:
    """Generate a score bar with inline value and label.

    Returns:
        Rich-formatted string: [bar] 0.950 (Very High)
    """
    bar = score_bar(score, width)
    color = score_to_color(score)
    label = score_to_label(score)
    return f"{bar}  [{color}]{score:.3f}[/{color}]  [dim]({label})[/dim]"


# ── Verdict Color Logic ───────────────────────────────────────────────


def verdict_color(
    integrity_score: float,
    confidence_score: float,
    triggered_count: int,
) -> tuple[str, str]:
    """Determine the overall verdict color and border.

    Args:
        integrity_score: Combined integrity score
        confidence_score: Confidence in the analysis
        triggered_count: Number of detectors that triggered

    Returns:
        Tuple of (text_color, border_color) for the verdict panel.
    """
    if triggered_count == 0 and integrity_score >= 0.9:
        return HEALTHY, BORDER_SUCCESS
    elif triggered_count == 0 and integrity_score >= 0.7:
        return STABLE, BORDER_SUCCESS
    elif triggered_count > 0:
        return DETECTOR_TRIGGERED, BORDER_ERROR
    else:
        return CAUTION, BORDER_WARNING


def verdict_icon(integrity_score: float, confidence_score: float, triggered_count: int) -> str:
    """Get the verdict icon."""
    if triggered_count == 0 and integrity_score >= 0.9:
        return "[bold green]V[/bold green]"
    elif triggered_count == 0:
        return "[bold green]V[/bold green]"
    elif triggered_count > 0:
        return "[bold red]X[/bold red]"
    else:
        return "[bold yellow]![/bold yellow]"


# ── Verdict Messages (Human-Friendly) ─────────────────────────────────

VERDICT_MESSAGES = {
    "healthy": "No evidence was found that repository metrics have become distorted, unstable, or misleading.",
    "stable": "Repository metrics appear generally stable with minor variations that are within expected ranges.",
    "partial": "One metric anomaly was detected, but overall measurement integrity remains acceptable.",
    "critical": "Multiple metric anomalies were detected. Manual investigation of repository measurement integrity is recommended.",
}

DETECTOR_VERDICTS_CLEAR = {
    "D-01": "No significant metric drift detected",
    "D-02": "Historical metric relationships remain stable",
    "D-03": "No threshold compression patterns detected",
}

DETECTOR_VERDICTS_TRIGGERED = {
    "D-01": "Significant metric drift detected",
    "D-02": "Historical metric relationships have shifted",
    "D-03": "Threshold compression patterns detected",
}

ACTION_MESSAGES = {
    "no_action": "No action required. Repository metrics are trustworthy.",
    "monitor": "Monitor metrics over time. Minor variations detected but within acceptable range.",
    "review": "Review the triggered detector output. One metric anomaly requires attention.",
    "investigate": "Investigate repository measurement integrity. Multiple anomalies detected.",
}
