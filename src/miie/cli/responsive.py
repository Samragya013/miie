"""Responsive Layout Engine for MIIE Terminal UI.

Adapts the UI to terminal width based on research:

- Nielsen (1993): Users scan, don't read. Layout must support scanning.
- Tullis (2011): Information density must match display width.
- Shneiderman (1998): Overview first, zoom and filter, details on demand.

Terminal Width Categories:
- Ultra-narrow:  < 60 cols  — emergency/minimal mode
- Narrow:        60-79 cols — compact mode (single column)
- Standard:      80-99 cols — default mode (standard layout)
- Wide:          100-119 cols — comfortable (wider columns)
- Ultra-wide:    >= 120 cols — full mode (multi-column possible)

Layout Strategy:
- Tables adapt column count to width
- Panels use available width
- Score bars scale proportionally
- Section headers truncate gracefully
- Metadata rows collapse to essential info only
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any


class WidthCategory(Enum):
    """Terminal width categories for layout selection."""

    ULTRA_NARROW = "ultra_narrow"  # < 60 cols
    NARROW = "narrow"  # 60-79 cols
    STANDARD = "standard"  # 80-99 cols
    WIDE = "wide"  # 100-119 cols
    ULTRA_WIDE = "ultra_wide"  # >= 120 cols


@dataclass
class LayoutConfig:
    """Layout configuration for a specific terminal width category.

    Attributes:
        score_bar_width: Characters for score visualization
        table_columns: Whether to show optional table columns
        panel_padding: Rich Panel padding tuple
        show_detail: Whether to show detail/verbose columns
        show_timing: Whether to show timing information
        max_detail_length: Truncation length for detail strings
        section_width: Width for section dividers
    """

    category: WidthCategory
    score_bar_width: int
    show_detail: bool
    show_timing: bool
    show_metadata: bool
    max_detail_length: int
    section_width: int
    table_min_widths: dict[str, int]


# ── Layout Presets ─────────────────────────────────────────────────────

LAYOUTS: dict[WidthCategory, LayoutConfig] = {
    WidthCategory.ULTRA_NARROW: LayoutConfig(
        category=WidthCategory.ULTRA_NARROW,
        score_bar_width=10,
        show_detail=False,
        show_timing=False,
        show_metadata=False,
        max_detail_length=15,
        section_width=50,
        table_min_widths={"id": 4, "name": 12, "status": 8},
    ),
    WidthCategory.NARROW: LayoutConfig(
        category=WidthCategory.NARROW,
        score_bar_width=14,
        show_detail=True,
        show_timing=False,
        show_metadata=False,
        max_detail_length=25,
        section_width=56,
        table_min_widths={"id": 5, "name": 16, "status": 10, "detail": 20},
    ),
    WidthCategory.STANDARD: LayoutConfig(
        category=WidthCategory.STANDARD,
        score_bar_width=20,
        show_detail=True,
        show_timing=True,
        show_metadata=True,
        max_detail_length=35,
        section_width=58,
        table_min_widths={"id": 6, "name": 20, "status": 12, "detail": 25, "time": 8},
    ),
    WidthCategory.WIDE: LayoutConfig(
        category=WidthCategory.WIDE,
        score_bar_width=28,
        show_detail=True,
        show_timing=True,
        show_metadata=True,
        max_detail_length=45,
        section_width=70,
        table_min_widths={"id": 6, "name": 22, "status": 14, "detail": 35, "time": 10},
    ),
    WidthCategory.ULTRA_WIDE: LayoutConfig(
        category=WidthCategory.ULTRA_WIDE,
        score_bar_width=36,
        show_detail=True,
        show_timing=True,
        show_metadata=True,
        max_detail_length=60,
        section_width=80,
        table_min_widths={"id": 6, "name": 25, "status": 16, "detail": 50, "time": 12},
    ),
}


# ── Layout Engine ──────────────────────────────────────────────────────


def get_terminal_width() -> int:
    """Get terminal width with safe fallback."""
    try:
        return os.get_terminal_size().columns
    except (OSError, ValueError):
        return 80


def classify_width(columns: int) -> WidthCategory:
    """Classify terminal width into a category.

    Args:
        columns: Terminal width in columns

    Returns:
        WidthCategory enum value.
    """
    if columns < 60:
        return WidthCategory.ULTRA_NARROW
    elif columns < 80:
        return WidthCategory.NARROW
    elif columns < 100:
        return WidthCategory.STANDARD
    elif columns < 120:
        return WidthCategory.WIDE
    else:
        return WidthCategory.ULTRA_WIDE


def get_layout(columns: int | None = None) -> LayoutConfig:
    """Get the layout configuration for current or specified terminal width.

    Args:
        columns: Override terminal width detection

    Returns:
        LayoutConfig for the detected width category.
    """
    width = columns if columns is not None else get_terminal_width()
    category = classify_width(width)
    return LAYOUTS[category]


# ── Adaptive Table Builder ────────────────────────────────────────────


def adapt_table_columns(
    columns: list[tuple[str, int]],
    available_width: int,
    priority_columns: list[str] | None = None,
) -> list[tuple[str, int]]:
    """Adapt table columns to fit available width.

    Drops low-priority columns if width is insufficient,
    then adjusts remaining column widths proportionally.

    Args:
        columns: List of (column_name, min_width) pairs
        available_width: Total available width in characters
        priority_columns: Column names in priority order (highest first)

    Returns:
        List of (column_name, adapted_width) pairs.
    """
    if priority_columns is None:
        priority_columns = [name for name, _ in columns]

    # Calculate total minimum width
    total_min = sum(width for _, width in columns)

    if total_min <= available_width:
        # All columns fit — distribute extra space proportionally
        extra = available_width - total_min
        result = []
        for name, min_width in columns:
            share = int(extra * (min_width / total_min)) if total_min > 0 else 0
            result.append((name, min_width + share))
        return result

    # Need to drop columns — remove lowest priority first
    included = list(columns)
    for col_name in reversed(priority_columns):
        if total_min <= available_width:
            break
        # Find and remove lowest priority column still in list
        for i, (name, width) in enumerate(included):
            if name == col_name and len(included) > 2:
                total_min -= width
                included.pop(i)
                break

    # Redistribute remaining width
    if included:
        remaining = available_width
        result = []
        for i, (name, min_width) in enumerate(included):
            if i == len(included) - 1:
                # Last column gets remaining space
                result.append((name, remaining))
            else:
                share = max(min_width, int(available_width * (min_width / total_min))) if total_min > 0 else min_width
                result.append((name, share))
                remaining -= share
        return result

    return columns


# ── Content Truncation ────────────────────────────────────────────────


def truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to max_length, adding suffix if truncated.

    Args:
        text: Input text
        max_length: Maximum character count
        suffix: Suffix to append when truncated

    Returns:
        Truncated text with suffix, or original if short enough.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def pad_or_truncate(text: str, width: int, align: str = "left") -> str:
    """Pad or truncate text to exact width.

    Args:
        text: Input text
        width: Target character width
        align: "left", "center", or "right"

    Returns:
        Text adjusted to exact width.
    """
    if len(text) > width:
        return text[:width]

    if align == "center":
        return text.center(width)
    elif align == "right":
        return text.rjust(width)
    else:
        return text.ljust(width)
