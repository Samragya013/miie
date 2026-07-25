"""Flagship Brand Header for MIIE Terminal UI.

Renders the permanent brand identity at the top of every screen.
Based on terminal UX research:

- LazyGit: Compact header with repo name + status
- K9s: Namespace/cluster header always visible
- gh CLI: Clean product identity in output
- btop: System info bar at top

The header adapts to terminal width:
- >= 120 cols: Full banner with logo
- >= 80 cols: Compact header with product name
- <  80 cols: Minimal single-line identity

All rendering uses Rich for consistent styling and
cp1252-compatible ASCII characters.
"""

from __future__ import annotations

import os
from typing import Literal

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .design_tokens import (
    COLOR_ACCENT,
    COLOR_BORDER_PRIMARY,
    COLOR_EVIDENCE,
    COLOR_LABEL,
    TOKENS,
)

# ── Logo Variants ──────────────────────────────────────────────────────
# Derived from the hash-block MIIE logotype, optimized for terminal
# rendering. Each variant serves a different width category.

LOGO_WIDE = r"""
   ####    ####  ##########  ##########  ##########  ##########
   ####    ####  ##########  ##########  ##########  ##########
   ##  ##  ##    ##          ##          ##          ##########
   ##   ####     ##  ######  ##  ######  ##  ######  ##########
   ##    ###     ##  ######  ##  ######  ##  ######  ##      ##
   ##     ##     ##  ######  ##  ######  ##  ######  ##      ##
   ##            ##          ##          ##          ##########
   ##            ##########  ##########  ##########  ##########"""

LOGO_COMPACT = r"""
   ####  ##########  ##########  ##########
   ##      ##          ##          ##########
   ##  ##  ##########  ##########  ##########
   ##      ##  ######  ##  ######  ##      ##
   ##      ##########  ##########  ##########"""

LOGO_MINIMAL = "M I I E"


# ── Header Data ────────────────────────────────────────────────────────

HEADER_SUBTITLE = "Measurement Integrity Intelligence Engine"
HEADER_CERTIFICATION = "Scientific"
HEADER_STATUS_LABEL = "Status"


# ── Adaptive Header Renderer ──────────────────────────────────────────


def get_terminal_width() -> int:
    """Get terminal width with safe fallback."""
    try:
        return os.get_terminal_size().columns
    except (OSError, ValueError):
        return 80


def render_brand_header(
    version: str,
    repo_name: str = "",
    status: str = "",
    terminal_width: int | None = None,
    variant: Literal["full", "compact", "minimal"] | None = None,
) -> Panel:
    """Render the flagship brand header.

    Adapts to terminal width:
    - full:   >= 100 cols — logo + subtitle + metadata
    - compact: >= 70 cols — product name + metadata
    - minimal: < 70 cols  — single line identity

    Args:
        version: MIIE version string
        repo_name: Current repository name (optional)
        status: Status message (optional)
        terminal_width: Override terminal width detection
        variant: Force a specific header variant

    Returns:
        Rich Panel containing the branded header.
    """
    width = terminal_width or get_terminal_width()

    if variant is None:
        if width >= 100:
            variant = "full"
        elif width >= 70:
            variant = "compact"
        else:
            variant = "minimal"

    if variant == "full":
        return _render_full_header(version, repo_name, status, width)
    elif variant == "compact":
        return _render_compact_header(version, repo_name, status, width)
    else:
        return _render_minimal_header(version, repo_name, status)


def _render_full_header(
    version: str,
    repo_name: str,
    status: str,
    width: int,
) -> Panel:
    """Full header with logo, subtitle, and metadata table."""
    content_parts: list[Text | Table] = []

    # Logo
    logo_text = Text()
    logo_lines = LOGO_WIDE.strip().split("\n")
    for i, line in enumerate(logo_lines):
        style = COLOR_ACCENT if i % 2 == 0 else "bold bright_white"
        logo_text.append(f"{line}\n", style=style)
    content_parts.append(logo_text)

    # Subtitle
    subtitle = Text()
    subtitle.append(f"  {HEADER_SUBTITLE}", style=COLOR_LABEL)
    subtitle.append(f"  v{version}", style="bold white")
    content_parts.append(subtitle)

    # Metadata row (if any metadata provided)
    if repo_name or status:
        meta = Table(show_header=False, box=None, padding=(0, 2), expand=True)
        meta.add_column("Key", style="dim", min_width=10)
        meta.add_column("Value", style="bold")
        if repo_name:
            meta.add_row("Repository", repo_name)
        if status:
            meta.add_row(HEADER_STATUS_LABEL, status)
        content_parts.append(meta)

    content = Group(*content_parts)

    return Panel(
        content,
        border_style=COLOR_BORDER_PRIMARY,
        padding=(0, 1),
        expand=True,
    )


def _render_compact_header(
    version: str,
    repo_name: str,
    status: str,
    width: int,
) -> Panel:
    """Compact header with product name and metadata."""
    content_parts: list[Text | Table] = []

    # Product identity
    identity = Text()
    identity.append(" MIIE ", style="bold white on bright_cyan")
    identity.append(f" v{version} ", style="bold")
    identity.append(f" {HEADER_SUBTITLE}", style=COLOR_LABEL)
    content_parts.append(identity)

    # Metadata
    if repo_name or status:
        meta = Table(show_header=False, box=None, padding=(0, 2), expand=True)
        meta.add_column("Key", style="dim", min_width=10)
        meta.add_column("Value", style="bold")
        if repo_name:
            meta.add_row("Repository", repo_name)
        if status:
            meta.add_row(HEADER_STATUS_LABEL, status)
        content_parts.append(meta)

    content = Group(*content_parts)

    return Panel(
        content,
        border_style=COLOR_BORDER_PRIMARY,
        padding=(0, 1),
        expand=True,
    )


def _render_minimal_header(
    version: str,
    repo_name: str,
    status: str,
) -> Panel:
    """Minimal single-line header for narrow terminals."""
    identity = Text()
    identity.append(" MIIE ", style="bold white on bright_cyan")
    identity.append(f"v{version}", style="bold")
    if repo_name:
        identity.append(f" | {repo_name}", style=COLOR_LABEL)
    if status:
        identity.append(f" | {status}", style=COLOR_EVIDENCE)

    return Panel(
        identity,
        border_style=COLOR_BORDER_PRIMARY,
        padding=(0, 0),
        expand=False,
    )


# ── Status Bar (Bottom) ────────────────────────────────────────────────


def render_status_bar(
    left_items: list[tuple[str, str]] | None = None,
    right_items: list[tuple[str, str]] | None = None,
    terminal_width: int | None = None,
) -> Text:
    """Render a status bar with items distributed across the width.

    Args:
        left_items: List of (label, value) pairs for left side
        right_items: List of (label, value) pairs for right side
        terminal_width: Override terminal width

    Returns:
        Rich Text object for the status bar.
    """
    width = terminal_width or get_terminal_width()

    bar = Text()

    # Left items
    if left_items:
        for i, (label, value) in enumerate(left_items):
            if i > 0:
                bar.append("  ", style="dim")
            bar.append(f"{label}: ", style="dim")
            bar.append(value, style="bold")

    # Fill to width
    left_len = sum(len(l) + len(v) + 2 for l, v in (left_items or []))
    right_len = sum(len(l) + len(v) + 2 for l, v in (right_items or []))
    fill = max(0, width - left_len - right_len - 4)
    bar.append(" " * fill, style="dim")

    # Right items
    if right_items:
        for i, (label, value) in enumerate(right_items):
            if i > 0:
                bar.append("  ", style="dim")
            bar.append(f"{label}: ", style="dim")
            bar.append(value, style="bold")

    return bar


# ── Section Divider ────────────────────────────────────────────────────


def render_section_divider(
    title: str,
    width: int | None = None,
    style: str = "bold cyan",
) -> Text:
    """Render a section divider with title.

    Pattern: ─── Title ────────────────────────────────

    Args:
        title: Section title text
        width: Total width (defaults to terminal width)
        style: Rich style for the divider

    Returns:
        Rich Text object.
    """
    w = (width or get_terminal_width()) - 4  # Account for indent
    title_len = len(title) + 2  # Space around title
    fill = max(0, w - title_len - 2)

    text = Text()
    text.append("  ", style="")
    text.append("-" * 2, style=style)
    text.append(f" {title} ", style=style)
    text.append("-" * fill, style="dim")

    return text
