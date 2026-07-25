"""Rich display components for MIIE CLI.

Provides panels, tables, progress bars, spinners, and formatted output
for the MIIE scientific analysis pipeline.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# Import branding
from .branding import (
    LOGO_COMPACT,
    LOGO_FULL,
    LOGO_FULL_DOUBLE,
    LOGO_FULL_TALL,
    LOGO_MINIMAL,
    PALETTE_PREMIUM,
)
from .branding import print_banner as _print_premium_banner
from .branding import (
    print_compact_banner,
)
from .branding import print_footer as _print_premium_footer
from .branding import (
    print_splash,
    print_startup_screen,
)

# ── Theme ──────────────────────────────────────────────────────────────
MIIE_THEME = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "metric": "bold blue",
        "score": "bold magenta",
        "dim": "dim white",
        "header": "bold white on dark_blue",
        "stage": "bold cyan",
        "pass": "bold green",
        "fail": "bold red",
        "skip": "bold yellow",
    }
)

# Configure console with Windows encoding support
# Force terminal mode when MIIE_FORCE_TERMINAL=1, or when running interactively
_force_terminal = os.environ.get("MIIE_FORCE_TERMINAL", "0") == "1" or os.isatty(1)
try:
    _width = min(120, os.get_terminal_size().columns if os.isatty(1) else 120)
except (OSError, ValueError):
    _width = 120
console = Console(
    theme=MIIE_THEME,
    force_terminal=_force_terminal,
    width=_width,
)


# ── Banner ─────────────────────────────────────────────────────────────
def print_banner(version: str, subtitle: str = "Measurement Integrity Intelligence Engine") -> None:
    """Print the premium MIIE header banner with ASCII art logo."""
    _print_premium_banner(version=version, subtitle=subtitle, variant="full")


def print_footer(message: str = "Analysis Complete", success: bool = True) -> None:
    """Print the MIIE footer."""
    _print_premium_footer(message=message, success=success)


# ── Dividers ───────────────────────────────────────────────────────────
def print_divider(style: str = "dim", char: str = "-", width: int | None = None) -> None:
    """Print a horizontal divider line."""
    if width is None:
        try:
            width = min(76, os.get_terminal_size().columns if os.isatty(1) else 76)
        except (OSError, ValueError):
            width = 76
    console.print(f"  [{style}]{char * width}[/{style}]")


def print_thick_divider(style: str = "cyan") -> None:
    """Print a thick section divider."""
    w = min(76, os.get_terminal_size().columns if os.isatty(1) else 76)
    console.print(f"  [{style}]{'=' * w}[/{style}]")


# ── Sections ───────────────────────────────────────────────────────────
_SECTION_ICONS = {
    "Analysis Coverage": "[cyan]>>[/cyan]",
    "Integrity Findings": "[yellow]>>[/yellow]",
    "Scientific Dashboard": "[blue]>>[/blue]",
    "Forensic Details": "[magenta]>>[/magenta]",
    "Reports Saved": "[green]>>[/green]",
    "Assessment": "[bold cyan]>>[/bold cyan]",
}


def print_section(title: str, icon: str | None = None) -> None:
    """Print a styled section header with optional icon."""
    console.print()
    icon_str = icon or _SECTION_ICONS.get(title, "[dim]>[/dim]")
    console.print(f"  {icon_str} [bold white]{title}[/bold white]")
    console.print(f"  [dim]{'-' * 50}[/dim]")


def print_kv(key: str, value: Any, indent: int = 2) -> None:
    """Print a key-value pair with aligned formatting."""
    padding = " " * indent
    console.print(f"  {padding}[dim]{key}:[/dim] [bold]{value}[/bold]")


def print_kv_aligned(key: str, value: Any, key_width: int = 18, indent: int = 2) -> None:
    """Print a key-value pair with fixed key width for alignment."""
    padding = " " * indent
    console.print(f"  {padding}{key:<{key_width}s} [bold]{value}[/bold]")


# ── Tables ─────────────────────────────────────────────────────────────
def make_table(title: str | None = None, **kwargs) -> Table:
    """Create a styled Rich table."""
    return Table(title=title, show_header=True, header_style="bold cyan", **kwargs)


def add_metric_row(
    table: Table,
    metric_id: str,
    name: str,
    value: Any,
    status: str = "ok",
) -> None:
    """Add a metric row to a table."""
    status_style = {
        "ok": "[green]●[/green]",
        "warn": "[yellow]●[/yellow]",
        "error": "[red]●[/red]",
        "skip": "[dim]○[/dim]",
    }.get(status, "[dim]?[/dim]")
    table.add_row(status_style, metric_id, name, str(value))


def add_detector_row(
    table: Table,
    detector_id: str,
    name: str,
    triggered: bool | None,
    detail: str = "",
) -> None:
    """Add a detector row to a table."""
    if triggered is None:
        status = "[yellow]SKIP[/yellow]"
    elif triggered:
        status = "[red]DETECTED[/red]"
    else:
        status = "[green]CLEAR[/green]"
    table.add_row(detector_id, name, status, detail)


# ── Panels ─────────────────────────────────────────────────────────────
def info_panel(title: str, content: str, style: str = "cyan") -> None:
    """Display an informational panel."""
    console.print(Panel(content, title=f"[bold]{title}[/bold]", border_style=style))


def success_panel(title: str, content: str) -> None:
    """Display a success panel."""
    console.print(Panel(content, title=f"[bold green]{title}[/bold green]", border_style="green"))


def error_panel(title: str, content: str) -> None:
    """Display an error panel."""
    console.print(Panel(content, title=f"[bold red]{title}[/bold red]", border_style="red"))


def warning_panel(title: str, content: str) -> None:
    """Display a warning panel."""
    console.print(Panel(content, title=f"[bold yellow]{title}[/bold yellow]", border_style="yellow"))


# ── Score Display ──────────────────────────────────────────────────────
def _score_rating(value: float, thresholds: tuple[float, float, float] = (0.9, 0.7, 0.5)) -> tuple[str, str]:
    """Return (color, rating) for a score value."""
    high, mid, low = thresholds
    if value >= high:
        return "green", "Very High"
    elif value >= mid:
        return "cyan", "High"
    elif value >= low:
        return "yellow", "Moderate"
    else:
        return "red", "Low"


def print_score(
    label: str,
    value: float,
    width: int = 30,
    thresholds: tuple[float, float, float] = (0.9, 0.7, 0.5),
) -> None:
    """Print a score with visual bar."""
    color, rating = _score_rating(value, thresholds)
    filled = int(value * width)
    bar = "#" * filled + "-" * (width - filled)
    console.print(f"  {label:<20s} [{color}]{bar}[/{color}] " f"[bold {color}]{value:.3f}[/bold {color}] ({rating})")


def print_score_premium(
    label: str,
    value: float,
    width: int = 36,
    thresholds: tuple[float, float, float] = (0.9, 0.7, 0.5),
) -> None:
    """Print a premium score with gradient bar and bold value."""
    color, rating = _score_rating(value, thresholds)
    filled = int(value * width)
    empty = width - filled

    # Build gradient-like bar using block chars
    # Use different shades: filled = solid blocks, empty = dots
    bar_filled = "#" * filled
    bar_empty = "." * empty

    console.print()
    console.print(f"  [bold white]{label}[/bold white]")
    console.print(
        f"    [{color}]{bar_filled}[/{color}][dim]{bar_empty}[/dim]"
        f"  [bold {color}]{value:.3f}[/bold {color}]"
        f"  [dim]({rating})[/dim]"
    )


def print_score_compact(
    label: str,
    value: float,
    width: int = 20,
    thresholds: tuple[float, float, float] = (0.9, 0.7, 0.5),
) -> None:
    """Print a compact score for inline use."""
    color, rating = _score_rating(value, thresholds)
    filled = int(value * width)
    bar = "#" * filled + "." * (width - filled)
    console.print(f"  [dim]{label}:[/dim] [{color}]{bar}[/{color}] [bold {color}]{value:.3f}[/bold {color}] ({rating})")


# ── Pipeline Stage Display ─────────────────────────────────────────────
def print_pipeline_stage(
    stage_num: int,
    total: int,
    name: str,
    status: str = "running",
    detail: str = "",
    elapsed: float | None = None,
) -> None:
    """Print a pipeline stage with status icon and progress bar."""
    icons = {
        "running": "[cyan]o[/cyan]",
        "done": "[green]V[/green]",
        "error": "[red]![/red]",
        "skip": "[yellow]-[/yellow]",
    }
    icon = icons.get(status, "[dim]?[/dim]")
    elapsed_str = f" [dim]({elapsed:.1f}s)[/dim]" if elapsed is not None else ""
    detail_str = f" [dim]-- {detail}[/dim]" if detail else ""

    # Progress bar
    progress = int((stage_num / total) * 20)
    filled = "#" * progress
    empty = "." * (20 - progress)

    if status == "running":
        console.print(f"    {icon} {stage_badge(stage_num, total)} [bold white]{name}[/bold white]")
        console.print(f"       [cyan]{filled}[/cyan][dim]{empty}[/dim] [dim]{stage_num}/{total}[/dim]")
    elif status == "done":
        console.print(
            f"    {icon} {stage_badge(stage_num, total)} [bold white]{name}[/bold white]{elapsed_str}{detail_str}"
        )
        console.print(f"       [green]{filled}[/green][dim]{empty}[/dim] [dim]{stage_num}/{total}[/dim]")
    elif status == "error":
        console.print(
            f"    {icon} {stage_badge(stage_num, total)} [bold red]{name}[/bold red]{elapsed_str} [red]{detail}[/red]"
        )
        console.print(f"       [red]{filled}[/red][dim]{empty}[/dim] [dim]{stage_num}/{total}[/dim]")
    else:
        console.print(f"    {icon} {stage_badge(stage_num, total)} [dim]{name}[/dim]{detail_str}")


def stage_badge(stage_num: int, total: int) -> str:
    """Create a stage number badge."""
    return f"[dim]{stage_num}/{total}[/dim]"


# ── Detection Summary ──────────────────────────────────────────────────
def print_detection_summary(
    detector_outputs: dict[str, Any],
    verbose: bool = False,
) -> None:
    """Print detector results with status icons."""
    _detector_names = {
        "D-01": "Distribution Drift",
        "D-02": "Correlation Breakdown",
        "D-03": "Threshold Compression",
    }
    for det_id in sorted(detector_outputs.keys()):
        det_data = detector_outputs[det_id]
        name = _detector_names.get(det_id, det_id)

        if not isinstance(det_data, dict):
            triggered = False
            failed = True
        elif det_data.get("status") in ("error", "skipped"):
            triggered = False
            failed = True
        else:
            failed = False
            triggered = (
                det_data.get("drift_detected")
                or det_data.get("breakdown_detected")
                or det_data.get("compression_detected", False)
            )

        if failed:
            reason = det_data.get("reason", "unknown") if isinstance(det_data, dict) else "unknown"
            console.print(f"    [yellow]![/yellow] [dim]{det_id}[/dim] {name}: [red]{reason[:60]}[/red]")
        elif triggered:
            console.print(f"    [red]X[/red] [dim]{det_id}[/dim] {name}: [red]DETECTED[/red]")
        else:
            console.print(f"    [green]V[/green] [dim]{det_id}[/dim] {name}: [green]CLEAR[/green]")


# ── Timestamp ──────────────────────────────────────────────────────────
def timestamp() -> str:
    """Return a formatted timestamp."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
