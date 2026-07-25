"""Keyboard navigation and interaction patterns for MIIE CLI.

Design principles:
- LazyGit: Single-key navigation, no modifier keys
- K9s: vim-like keybindings (j/k/Enter/q)
- gh CLI: Discoverable shortcuts via '?' help overlay

The scientific engine is frozen. This module handles UX only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rich.console import Console
from rich.text import Text

from .display import console


class FocusArea(Enum):
    """Navigable focus areas in the TUI."""

    PIPELINE = "pipeline"
    SCORES = "scores"
    DETECTORS = "detectors"
    EVIDENCE = "evidence"
    FOOTER = "footer"


class Action(Enum):
    """Available user actions."""

    NEXT = "next"
    PREV = "prev"
    DETAIL = "detail"
    EXPAND = "expand"
    COLLAPSE = "collapse"
    FILTER = "filter"
    SORT = "sort"
    EXPORT = "export"
    HELP = "help"
    QUIT = "quit"


# ── Keybinding Maps ───────────────────────────────────────────────────

# Minimal keys: no modifiers, no function keys, no escape sequences
# Inspired by LazyGit's single-key navigation model
KEYBINDINGS: dict[str, Action] = {
    # Navigation
    "j": Action.NEXT,
    "k": Action.PREV,
    "tab": Action.NEXT,
    "shift_tab": Action.PREV,
    # Detail
    "enter": Action.DETAIL,
    "space": Action.EXPAND,
    "escape": Action.COLLAPSE,
    # Filter & sort
    "/": Action.FILTER,
    "s": Action.SORT,
    # Actions
    "e": Action.EXPORT,
    "?": Action.HELP,
    "q": Action.QUIT,
}


@dataclass
class NavigationState:
    """Current navigation state of the TUI."""

    focus: FocusArea = FocusArea.PIPELINE
    expanded: bool = False
    filter_active: bool = False
    filter_text: str = ""
    sort_key: str = "severity"
    help_visible: bool = False

    # Focus order (top to bottom)
    _focus_order: list[FocusArea] = field(
        default_factory=lambda: [
            FocusArea.PIPELINE,
            FocusArea.SCORES,
            FocusArea.DETECTORS,
            FocusArea.EVIDENCE,
            FocusArea.FOOTER,
        ]
    )

    def next_focus(self) -> None:
        """Move focus to next area."""
        idx = self._focus_order.index(self.focus)
        self.focus = self._focus_order[(idx + 1) % len(self._focus_order)]
        self.expanded = False

    def prev_focus(self) -> None:
        """Move focus to previous area."""
        idx = self._focus_order.index(self.focus)
        self.focus = self._focus_order[(idx - 1) % len(self._focus_order)]
        self.expanded = False

    def toggle_expand(self) -> None:
        """Toggle expanded detail view."""
        self.expanded = not self.expanded

    def toggle_help(self) -> None:
        """Toggle help overlay."""
        self.help_visible = not self.help_visible

    def cycle_sort(self) -> None:
        """Cycle through sort keys."""
        keys = ["severity", "name", "value", "delta"]
        idx = keys.index(self.sort_key) if self.sort_key in keys else 0
        self.sort_key = keys[(idx + 1) % len(keys)]


# ── Help Overlay ──────────────────────────────────────────────────────

HELP_CONTENT = {
    "Navigation": {
        "j / Tab": "Next section",
        "k / Shift-Tab": "Previous section",
        "Enter": "Show details",
        "Space": "Expand / Collapse",
        "Esc": "Collapse detail",
    },
    "Actions": {
        "/": "Filter results",
        "s": "Cycle sort order",
        "e": "Export results",
        "q": "Quit",
    },
    "Focus Areas": {
        "Pipeline": "Stage progress & timing",
        "Scores": "Integrity & confidence",
        "Detectors": "D-01 / D-02 / D-03 status",
        "Evidence": "Statistical evidence details",
    },
}


def render_help_overlay(state: NavigationState) -> Text:
    """Render the help overlay for keyboard shortcuts."""
    text = Text()
    text.append("\n  Keyboard Shortcuts\n", style="bold cyan")
    text.append("  " + "=" * 44 + "\n", style="dim")

    for section, bindings in HELP_CONTENT.items():
        text.append(f"\n  {section}\n", style="bold")
        for key, desc in bindings.items():
            text.append(f"    {key:12s} ", style="cyan")
            text.append(f"{desc}\n", style="")

    text.append(f"\n  Current: {state.focus.value}\n", style="dim")
    text.append(f"  Sort: {state.sort_key}\n", style="dim")
    if state.filter_active:
        text.append(f"  Filter: {state.filter_text}\n", style="yellow")

    text.append("\n  Press ? to close\n", style="dim")

    return text


# ── Focus Indicator ───────────────────────────────────────────────────


def render_focus_indicator(area: FocusArea, is_focused: bool) -> Text:
    """Render a focus indicator for a section."""
    text = Text()
    if is_focused:
        text.append(" > ", style="bold cyan")
    else:
        text.append("   ", style="dim")
    return text


# ── Filter Bar ────────────────────────────────────────────────────────


def render_filter_bar(text: str) -> Text:
    """Render the filter input bar."""
    bar = Text()
    bar.append("  / ", style="bold cyan")
    bar.append(text, style="bold white")
    bar.append("_", style="blink white")
    return bar


# ── Sort Indicator ────────────────────────────────────────────────────

SORT_ICONS = {
    "severity": "!",
    "name": "A",
    "value": "#",
    "delta": "~",
}


def render_sort_indicator(sort_key: str) -> Text:
    """Render the current sort mode."""
    icon = SORT_ICONS.get(sort_key, "?")
    text = Text()
    text.append(f"  [{icon}] ", style="cyan")
    text.append(f"Sort: {sort_key}", style="dim")
    return text
