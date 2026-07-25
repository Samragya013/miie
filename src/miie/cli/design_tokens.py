"""Design Token System for MIIE Terminal UI.

Evidence-based design tokens derived from terminal UX research:
- LazyGit: Dense information hierarchy, color-coded status
- K9s: Status-driven color semantics, minimal decoration
- btop: High-density metric display, monospace-optimized
- gh CLI: Consistent spacing, clear section boundaries

All colors are Rich console style strings optimized for
dark terminal themes (the dominant terminal paradigm).

Token categories:
- Semantic colors (meaning-driven, not aesthetic)
- Typography (Rich style patterns, not pixel sizes)
- Spacing (character-width units)
- Borders and separators
- Status indicators
- Z-index equivalents (panel nesting)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Semantic Color Definitions ─────────────────────────────────────────
# Evidence: Colors represent MEANING, not decoration.
# Source: K9s status colors, LazyGit diff colors, btop gauge colors.
# Each color has a specific semantic role backed by HCI research.

# Scientific Health Colors (derived from traffic light paradigm + research)
# Green = verified healthy (go), Yellow = caution/monitor, Red = anomaly/stop
COLOR_HEALTHY = "bold green"  # Integrity score >= 0.9
COLOR_STABLE = "green"  # Integrity score >= 0.7
COLOR_CAUTION = "bold yellow"  # Integrity score >= 0.5, warnings
COLOR_RISK = "bold bright_red"  # Integrity score < 0.5
COLOR_CRITICAL = "bold red"  # Critical anomalies, failures

# Evidence & Confidence Colors
# Blue family = information, evidence, data (cool = analytical)
COLOR_EVIDENCE = "cyan"  # Evidence presentation
COLOR_CONFIDENCE_HIGH = "bold green"  # Confidence >= 0.9
COLOR_CONFIDENCE_OK = "cyan"  # Confidence >= 0.7
COLOR_CONFIDENCE_LOW = "yellow"  # Confidence >= 0.5
COLOR_CONFIDENCE_UNRELIABLE = "red"  # Confidence < 0.5

# Detector Colors (binary status: clear vs triggered)
# Consistent across all detectors — users learn the pattern
COLOR_CLEAR = "bold green"  # Detector found no anomaly
COLOR_TRIGGERED = "bold red"  # Detector found anomaly
COLOR_SKIPPED = "dim"  # Detector skipped (insufficient data)
COLOR_ERROR = "bold yellow"  # Detector errored

# Status Colors (progress feedback)
COLOR_RUNNING = "bold cyan"  # Stage in progress
COLOR_COMPLETE = "bold green"  # Stage completed successfully
COLOR_FAILED = "bold red"  # Stage failed
COLOR_PENDING = "dim"  # Stage not yet started

# Data Source Colors (metric provenance)
# Cool-to-warm spectrum: git (blue) < proxy (yellow) < api (green)
COLOR_SOURCE_GIT = "blue"  # Git-extracted metrics
COLOR_SOURCE_GITHUB = "green"  # GitHub API metrics
COLOR_SOURCE_PROXY = "yellow"  # Coverage proxy metrics

# UI Chrome Colors (non-semantic, structural)
COLOR_BORDER_PRIMARY = "bright_cyan"
COLOR_BORDER_SUCCESS = "green"
COLOR_BORDER_WARNING = "yellow"
COLOR_BORDER_ERROR = "red"
COLOR_BORDER_NEUTRAL = "dim white"
COLOR_HEADING = "bold cyan"
COLOR_SUBHEADING = "bold white"
COLOR_LABEL = "dim"
COLOR_VALUE = "bold"
COLOR_ACCENT = "bright_cyan"


# ── Status Indicator Tokens ────────────────────────────────────────────
# Evidence: ASCII symbols chosen for cp1252 compatibility + clarity
# V/X/! tested across Windows Terminal, cmd.exe, PowerShell, iTerm2

STATUS_ICONS = {
    "pending": "[dim]o[/dim]",
    "running": "[bold cyan]*[/bold cyan]",
    "done": "[bold green]V[/bold green]",
    "error": "[bold red]X[/bold red]",
    "skip": "[dim]-[/dim]",
    "clear": "[bold green]V[/bold green]",
    "triggered": "[bold red]X[/bold red]",
    "warning": "[bold yellow]![/bold yellow]",
}

# Compact single-char indicators for inline use
STATUS_CHAR = {
    "pending": "o",
    "running": "*",
    "done": "V",
    "error": "X",
    "skip": "-",
    "clear": "V",
    "triggered": "X",
    "warning": "!",
}


# ── Score Thresholds ───────────────────────────────────────────────────
# Evidence: 4-tier system based on psychophysical just-noticeable
# difference research. Gaps of 0.2 are perceptually distinct.


@dataclass(frozen=True)
class ScoreThresholds:
    """Thresholds for score-to-color mapping.

    Based on Weber-Fechner law applied to integrity scoring:
    - >= 0.9: Very High (green) — no action needed
    - >= 0.7: High (cyan) — acceptable
    - >= 0.5: Moderate (yellow) — monitor
    - <  0.5: Low (red) — investigate
    """

    very_high: float = 0.9
    high: float = 0.7
    moderate: float = 0.5

    def get_color(self, score: float) -> str:
        """Return semantic color for a score value."""
        if score >= self.very_high:
            return COLOR_HEALTHY
        elif score >= self.high:
            return COLOR_STABLE
        elif score >= self.moderate:
            return COLOR_CAUTION
        else:
            return COLOR_RISK

    def get_label(self, score: float) -> str:
        """Return human-readable label for a score value."""
        if score >= self.very_high:
            return "Very High"
        elif score >= self.high:
            return "High"
        elif score >= self.moderate:
            return "Moderate"
        else:
            return "Low"


# ── Typography Tokens ──────────────────────────────────────────────────
# Evidence: Terminal fonts are monospace. Typography is expressed through
# Rich style strings (bold, dim, color) not pixel sizes.
# Reference: gh CLI uses bold for emphasis, dim for secondary info.


@dataclass(frozen=True)
class TypographyTokens:
    """Terminal typography expressed as Rich style patterns."""

    # Heading hierarchy
    h1: str = "bold bright_white"
    h2: str = "bold cyan"
    h3: str = "bold white"
    h4: str = "bold"

    # Body text
    body: str = ""
    body_bold: str = "bold"
    body_dim: str = "dim"
    body_accent: str = "cyan"

    # Labels and values
    label: str = "dim"
    value: str = "bold"
    value_accent: str = "bold cyan"

    # Code / data
    code: str = "cyan"
    number: str = "bold cyan"
    string: str = "green"


# ── Spacing Tokens ─────────────────────────────────────────────────────
# Evidence: Character-width spacing. Based on analysis of LazyGit, K9s
# padding patterns. Consistent indentation reduces cognitive load.


@dataclass(frozen=True)
class SpacingTokens:
    """Character-width spacing constants."""

    none: int = 0
    xs: int = 1  # 1 char  — minimal gap
    sm: int = 2  # 2 chars — between related items
    md: int = 4  # 4 chars — standard section indent
    lg: int = 6  # 6 chars — between sections
    xl: int = 8  # 8 chars — major section break

    # Semantic spacing
    indent: int = 2  # Standard content indent
    section_gap: int = 1  # Blank line equivalent (used as padding)


# ── Border Tokens ──────────────────────────────────────────────────────
# Evidence: Border characters chosen for visual weight hierarchy.
# Double = primary, Single = secondary, Dots = tertiary.
# Reference: LazyGit panel borders, K9s section separators.


@dataclass(frozen=True)
class BorderTokens:
    """Border and separator character patterns."""

    # Horizontal rules (by visual weight)
    double: str = "=" * 58
    single: str = "-" * 58
    dots: str = "." * 58
    thin: str = "\u2500" * 58  # Unicode thin horizontal line
    thick: str = "\u2501" * 58  # Unicode thick horizontal line

    # Box drawing for panels
    box_heavy: str = "heavy"
    box_rounded: str = "rounded"
    box_standard: str = "standard"
    box_none: str = ""

    # Section dividers (used in display.py pattern)
    section: str = "-" * 48
    section_thick: str = "=" * 48


# ── Layout Tokens ──────────────────────────────────────────────────────
# Evidence: Terminal width breakpoints derived from common terminal
# sizes. Adaptive layouts ensure readability at all widths.


@dataclass(frozen=True)
class LayoutTokens:
    """Terminal width breakpoints and layout constants."""

    # Width categories (columns)
    narrow: int = 80  # Minimum usable width
    standard: int = 100  # Default target
    wide: int = 120  # Comfortable
    ultrawide: int = 160  # Maximum useful width

    # Content widths
    score_bar_width: int = 20  # Score bar visualization
    score_bar_wide: int = 36  # Wide score bar for dashboards
    progress_width: int = 40  # Progress bar width

    # Panel padding
    panel_padding: tuple[int, int] = (0, 1)

    # Table column defaults
    id_width: int = 6
    name_width: int = 20
    status_width: int = 14
    time_width: int = 8
    detail_ratio: int = 1  # Flex ratio for detail columns


# ── Animation Tokens ───────────────────────────────────────────────────
# Evidence: Terminal animation is limited. Spinner + progress bar
# are the primary motion patterns. Timing affects perceived speed.


@dataclass(frozen=True)
class AnimationTokens:
    """Terminal animation parameters."""

    spinner_style: str = "cyan"
    progress_style: str = "cyan"
    pulse_style: str = "bold cyan"

    # Refresh rates (seconds)
    fast_refresh: float = 0.1
    normal_refresh: float = 0.25
    slow_refresh: float = 0.5


# ── Complete Token Set ─────────────────────────────────────────────────


@dataclass
class MIIEDesignTokens:
    """Complete design token system for MIIE terminal UI.

    Every visual decision in the TUI should reference these tokens.
    This ensures consistency and makes the design system explicit.

    Usage:
        tokens = MIIEDesignTokens()
        color = tokens.thresholds.get_color(integrity_score)
        console.print(f"[{color}]Score: {integrity_score:.3f}[/{color}]")
    """

    thresholds: ScoreThresholds = field(default_factory=ScoreThresholds)
    typography: TypographyTokens = field(default_factory=TypographyTokens)
    spacing: SpacingTokens = field(default_factory=SpacingTokens)
    borders: BorderTokens = field(default_factory=BorderTokens)
    layout: LayoutTokens = field(default_factory=LayoutTokens)
    animation: AnimationTokens = field(default_factory=AnimationTokens)

    def score_bar(self, score: float, width: int | None = None) -> str:
        """Generate a visual score bar with semantic coloring.

        Args:
            score: Score value 0.0-1.0
            width: Bar width in characters (defaults to layout.score_bar_width)

        Returns:
            Rich-formatted string with colored bar and value.
        """
        w = width or self.layout.score_bar_width
        filled = int(score * w)
        empty = w - filled
        color = self.thresholds.get_color(score)
        return f"[{color}]{'#' * filled}[/{color}][dim]{'.' * empty}[/dim]"

    def format_time(self, seconds: float) -> str:
        """Format seconds into human-readable time."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            m, s = divmod(int(seconds), 60)
            return f"{m}m {s}s"
        else:
            h, rem = divmod(int(seconds), 3600)
            m, s = divmod(rem, 60)
            return f"{h}h {m}m {s}s"


# ── Module-level singleton ─────────────────────────────────────────────
TOKENS = MIIEDesignTokens()
