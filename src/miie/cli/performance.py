"""Performance and interaction design for MIIE CLI TUI.

Handles:
- Render budget tracking (keep TUI overhead < 5% of total pipeline time)
- Minimal Rich object allocation (reuse tables, panels)
- Efficient string building for large outputs
- Progressive disclosure (summary first, details on demand)

The scientific engine is frozen. This module handles UX only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from rich.table import Table
from rich.text import Text


@dataclass
class RenderBudget:
    """Track TUI render time to stay within budget."""

    _budget_ms: float = 50.0  # 50ms total budget for TUI renders
    _spent_ms: float = 0.0
    _render_count: int = 0
    _warned: bool = False

    def start(self) -> float:
        """Start timing a render."""
        return time.perf_counter()

    def end(self, start: float) -> bool:
        """End timing. Returns True if within budget."""
        elapsed_ms = (time.perf_counter() - start) * 1000
        self._spent_ms += elapsed_ms
        self._render_count += 1
        if self._spent_ms > self._budget_ms and not self._warned:
            self._warned = True
            return False
        return True

    @property
    def remaining_ms(self) -> float:
        return max(0, self._budget_ms - self._spent_ms)

    @property
    def is_over_budget(self) -> bool:
        return self._spent_ms > self._budget_ms

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "renders": self._render_count,
            "total_ms": round(self._spent_ms, 2),
            "budget_ms": self._budget_ms,
            "remaining_ms": round(self.remaining_ms, 2),
            "over_budget": self.is_over_budget,
        }


# ── Table Reuse Pool ──────────────────────────────────────────────────


class TablePool:
    """Reuse Rich Table objects to reduce allocation overhead."""

    def __init__(self, max_size: int = 10) -> None:
        self._pool: dict[str, Table] = {}
        self._max_size = max_size

    def get(
        self,
        key: str,
        *,
        show_header: bool = True,
        header_style: str = "bold cyan",
        box: Any = None,
        padding: tuple[int, int] = (0, 1),
        expand: bool = False,
    ) -> Table:
        """Get or create a table with the given key."""
        if key in self._pool:
            table = self._pool[key]
            table.columns.clear()
            return table

        if len(self._pool) >= self._max_size:
            # Evict oldest
            oldest = next(iter(self._pool))
            del self._pool[oldest]

        table = Table(
            show_header=show_header,
            header_style=header_style,
            box=box,
            padding=padding,
            expand=expand,
        )
        self._pool[key] = table
        return table

    def clear(self) -> None:
        """Clear all pooled tables."""
        self._pool.clear()


# ── Progressive Disclosure ────────────────────────────────────────────


@dataclass
class DisclosureLevel:
    """Controls what detail level to show based on terminal width."""

    width: int = 80
    show_timing: bool = True
    show_detail: bool = True
    show_bars: bool = True
    show_purpose: bool = True
    max_rows: int = 50

    @classmethod
    def for_width(cls, width: int) -> DisclosureLevel:
        """Create disclosure level based on terminal width."""
        if width < 60:
            return cls(
                width=width, show_timing=False, show_detail=False, show_bars=False, show_purpose=False, max_rows=10
            )
        elif width < 80:
            return cls(
                width=width, show_timing=True, show_detail=False, show_bars=True, show_purpose=False, max_rows=20
            )
        elif width < 100:
            return cls(width=width, show_timing=True, show_detail=True, show_bars=True, show_purpose=False, max_rows=30)
        else:
            return cls(width=width, show_timing=True, show_detail=True, show_bars=True, show_purpose=True, max_rows=50)


# ── String Builder ────────────────────────────────────────────────────


class StringBuilder:
    """Efficient string building for large outputs."""

    def __init__(self) -> None:
        self._parts: list[str] = []

    def append(self, text: str) -> None:
        self._parts.append(text)

    def newline(self) -> None:
        self._parts.append("\n")

    def build(self) -> str:
        return "".join(self._parts)

    def clear(self) -> None:
        self._parts.clear()

    @property
    def length(self) -> int:
        return sum(len(p) for p in self._parts)


# ── Truncation ────────────────────────────────────────────────────────


def truncate(text: str, max_width: int, suffix: str = "...") -> str:
    """Truncate text with ellipsis, preserving ANSI codes."""
    if len(text) <= max_width:
        return text
    return text[: max_width - len(suffix)] + suffix


def pad_or_truncate(text: str, width: int, align: str = "left") -> str:
    """Pad or truncate text to exact width."""
    if len(text) >= width:
        return text[:width]
    padding = width - len(text)
    if align == "center":
        left = padding // 2
        right = padding - left
        return " " * left + text + " " * right
    elif align == "right":
        return " " * padding + text
    return text + " " * padding


# ── Global Instances ──────────────────────────────────────────────────

BUDGET = RenderBudget()
TABLE_POOL = TablePool()
