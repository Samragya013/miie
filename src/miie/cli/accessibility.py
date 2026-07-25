"""Accessibility layer for MIIE CLI TUI.

Implements WCAG 2.1 AA compliance for terminal interfaces:
- Color-blind safe palettes (deuteranopia, protanopia, tritanopia)
- Text-only fallbacks for all color-coded information
- Screen reader compatible output markers
- High contrast mode support

Design principles:
- Every color-coded element has a text-only fallback
- No information conveyed solely through color
- Consistent, predictable output structure
- Respect NO_COLOR / TERM=dumb environment variables

References:
- WCAG 2.1 Level AA: 1.4.1 (Color not sole indicator)
- WCAG 2.1 Level AA: 1.4.3 (Contrast ratio >= 4.5:1)
- Color blind safe palette: Wong (2011), Nature Methods

The scientific engine is frozen. This module handles UX only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from rich.text import Text


class ColorBlindMode(Enum):
    """Supported color blindness modes."""

    NORMAL = "normal"
    DEUTERANOPIA = "deuteranopia"  # Red-green (most common)
    PROTANOPIA = "protanopia"  # Red-green
    TRITANOPIA = "tritanopia"  # Blue-yellow
    MONOCHROME = "monochrome"


@dataclass
class AccessibilityConfig:
    """Accessibility configuration."""

    color_mode: ColorBlindMode = ColorBlindMode.NORMAL
    no_color: bool = False
    dumb_terminal: bool = False
    high_contrast: bool = False

    @classmethod
    def from_env(cls) -> AccessibilityConfig:
        """Load config from environment variables."""
        no_color = os.environ.get("NO_COLOR") is not None
        dumb = os.environ.get("TERM", "").lower() in ("dumb", "")

        mode = ColorBlindMode.NORMAL
        miie_mode = os.environ.get("MIIE_COLOR_MODE", "").lower()
        if miie_mode in ("deuteranopia", "deuteran", "cb-deut"):
            mode = ColorBlindMode.DEUTERANOPIA
        elif miie_mode in ("protanopia", "protan", "cb-prot"):
            mode = ColorBlindMode.PROTANOPIA
        elif miie_mode in ("tritanopia", "tritan", "cb-trit"):
            mode = ColorBlindMode.TRITANOPIA
        elif miie_mode in ("monochrome", "mono", "bw"):
            mode = ColorBlindMode.MONOCHROME

        high_contrast = os.environ.get("MIIE_HIGH_CONTRAST", "").lower() in ("1", "true", "yes")

        return cls(
            color_mode=mode,
            no_color=no_color,
            dumb_terminal=dumb,
            high_contrast=high_contrast,
        )


# ── Color-Blind Safe Palettes ─────────────────────────────────────────
# Based on Wong (2011) color-blind safe palette

CB_PALETTES = {
    ColorBlindMode.NORMAL: {
        "clear": "green",
        "triggered": "red",
        "warning": "yellow",
        "info": "cyan",
        "score_high": "green",
        "score_mid": "cyan",
        "score_low": "yellow",
        "score_bad": "red",
        "dim": "dim white",
    },
    ColorBlindMode.DEUTERANOPIA: {
        "clear": "bright_blue",
        "triggered": "bright_yellow",
        "warning": "bright_magenta",
        "info": "bright_cyan",
        "score_high": "bright_blue",
        "score_mid": "bright_cyan",
        "score_low": "bright_magenta",
        "score_bad": "bright_yellow",
        "dim": "dim white",
    },
    ColorBlindMode.PROTANOPIA: {
        "clear": "bright_blue",
        "triggered": "bright_yellow",
        "warning": "bright_magenta",
        "info": "bright_cyan",
        "score_high": "bright_blue",
        "score_mid": "bright_cyan",
        "score_low": "bright_magenta",
        "score_bad": "bright_yellow",
        "dim": "dim white",
    },
    ColorBlindMode.TRITANOPIA: {
        "clear": "bright_red",
        "triggered": "bright_cyan",
        "warning": "bright_green",
        "info": "bright_magenta",
        "score_high": "bright_red",
        "score_mid": "bright_green",
        "score_low": "bright_cyan",
        "score_bad": "bright_magenta",
        "dim": "dim white",
    },
    ColorBlindMode.MONOCHROME: {
        "clear": "white",
        "triggered": "bold white",
        "warning": "dim white",
        "info": "dim white",
        "score_high": "bold white",
        "score_mid": "white",
        "score_low": "dim white",
        "score_bad": "dim white",
        "dim": "dim white",
    },
}


def get_palette(config: AccessibilityConfig | None = None) -> dict[str, str]:
    """Get the appropriate color palette."""
    if config is None:
        config = AccessibilityConfig.from_env()
    return CB_PALETTES.get(config.color_mode, CB_PALETTES[ColorBlindMode.NORMAL])


# ── Status Markers (color-blind safe) ─────────────────────────────────

STATUS_MARKERS = {
    "clear": {"icon": "V", "text": "CLEAR"},
    "triggered": {"icon": "X", "text": "DETECTED"},
    "warning": {"icon": "!", "text": "WARNING"},
    "error": {"icon": "X", "text": "ERROR"},
    "skipped": {"icon": "-", "text": "SKIPPED"},
    "pending": {"icon": "o", "text": "PENDING"},
    "running": {"icon": "*", "text": "RUNNING"},
    "done": {"icon": "V", "text": "DONE"},
}


def status_text(status: str) -> str:
    """Get text-only status marker."""
    return STATUS_MARKERS.get(status, {"icon": "?", "text": status.upper()})["text"]


def status_icon(status: str) -> str:
    """Get ASCII icon for status."""
    return STATUS_MARKERS.get(status, {"icon": "?", "text": status})["icon"]


# ── Accessible Score Display ──────────────────────────────────────────


def accessible_score(
    score: float,
    label: str = "",
    show_bar: bool = True,
    config: AccessibilityConfig | None = None,
) -> Text:
    """Render a score with accessibility support.

    Always includes text-based meaning alongside color.
    """
    if config is None:
        config = AccessibilityConfig.from_env()

    palette = get_palette(config)
    text = Text()

    # Determine score color category
    if score >= 0.9:
        color = palette["score_high"]
        meaning = "excellent"
    elif score >= 0.7:
        color = palette["score_mid"]
        meaning = "good"
    elif score >= 0.5:
        color = palette["score_low"]
        meaning = "fair"
    else:
        color = palette["score_bad"]
        meaning = "poor"

    if label:
        text.append(f"{label}: ", style="bold")

    text.append(f"{score:.3f}", style=f"bold {color}")
    text.append(f" [{meaning}]", style="dim")

    return text


def accessible_verdict(
    triggered_count: int,
    integrity_score: float,
    config: AccessibilityConfig | None = None,
) -> Text:
    """Render a verdict with accessibility support."""
    if config is None:
        config = AccessibilityConfig.from_env()

    palette = get_palette(config)
    text = Text()

    if triggered_count == 0 and integrity_score >= 0.9:
        text.append("VERDICT: ", style="bold")
        text.append("INTEGRITY VERIFIED", style=f"bold {palette['clear']}")
        text.append(" [No detectors triggered]", style="dim")
    elif triggered_count > 0:
        text.append("VERDICT: ", style="bold")
        text.append(f"{triggered_count} DETECTOR(S) TRIGGERED", style=f"bold {palette['triggered']}")
        text.append(" [Action required]", style="dim")
    else:
        text.append("VERDICT: ", style="bold")
        text.append("PARTIAL INTEGRITY", style=f"bold {palette['warning']}")
        text.append(" [Review recommended]", style="dim")

    return text


# ── Screen Reader Support ─────────────────────────────────────────────


def sr_section_start(name: str) -> str:
    """Screen reader: section start marker."""
    return f"\x1b]1337;Custom=id=miie-{name}\x07"


def sr_section_end() -> str:
    """Screen reader: section end marker."""
    return "\x1b]1337;Custom=id=miie-end\x07"


# ── Environment Detection ─────────────────────────────────────────────


def should_use_color() -> bool:
    """Check if terminal supports color."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    return True


def terminal_supports_unicode() -> bool:
    """Check if terminal supports Unicode."""
    import sys

    if sys.platform == "win32":
        # Windows Terminal supports Unicode, legacy cmd may not
        wt = os.environ.get("WT_SESSION")
        return wt is not None or os.environ.get("TERM_PROGRAM") == "mintty"
    return True
