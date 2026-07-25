"""ASCII chart components for MIIE score visualization.

Provides bar charts, sparklines, and metric comparison tables
using only ASCII characters for maximum compatibility.
"""

from __future__ import annotations

from typing import Any

from .display import console, print_divider, print_section


# ── Bar Charts ─────────────────────────────────────────────────────────
def print_bar_chart(
    title: str,
    data: dict[str, float],
    width: int = 40,
    threshold_high: float = 0.9,
    threshold_mid: float = 0.7,
) -> None:
    """Print a horizontal bar chart with color coding.

    Args:
        title: Chart title
        data: {label: value} pairs (values 0.0-1.0)
        width: Maximum bar width in characters
        threshold_high: Value threshold for green color
        threshold_mid: Value threshold for yellow color
    """
    if not data:
        return

    print_section(title)

    # Calculate max label width for alignment
    max_label = max(len(k) for k in data.keys())
    label_width = min(max_label + 2, 24)

    for label, value in data.items():
        value = max(0.0, min(1.0, value))
        filled = int(value * width)
        empty = width - filled

        # Color based on thresholds
        if value >= threshold_high:
            color = "green"
        elif value >= threshold_mid:
            color = "cyan"
        elif value >= 0.5:
            color = "yellow"
        else:
            color = "red"

        bar = "#" * filled + "." * empty
        console.print(
            f"  {label:<{label_width}s} [{color}]{bar}[/{color}] " f"[bold {color}]{value:.3f}[/bold {color}]"
        )

    console.print()


def print_vertical_bar(
    label: str,
    value: float,
    height: int = 6,
    width: int = 20,
) -> None:
    """Print a single vertical bar (for sparkline-style display).

    Args:
        label: Bar label
        value: Value 0.0-1.0
        height: Height in rows
        width: Width in characters
    """
    filled = int(value * height)
    empty = height - filled

    # Choose character based on level
    if value >= 0.9:
        char, color = "#", "green"
    elif value >= 0.7:
        char, color = "#", "cyan"
    elif value >= 0.5:
        char, color = "=", "yellow"
    else:
        char, color = "-", "red"

    # Print from top to bottom
    for i in range(height):
        if i < empty:
            console.print(f"  [dim]  .[/dim]")
        else:
            console.print(f"  [{color}]  {char}[/{color}]")

    console.print(f"  [dim]{label[:width]}[/dim]")


# ── Sparkline ──────────────────────────────────────────────────────────
def sparkline(values: list[float], width: int = 30) -> str:
    """Generate an ASCII sparkline string.

    Args:
        values: List of numeric values
        width: Output width in characters

    Returns:
        ASCII sparkline string
    """
    if not values:
        return ""

    # Characters from low to high
    chars = " .:-=+*#%@"

    min_val = min(values)
    max_val = max(values)
    val_range = max_val - min_val

    if val_range == 0:
        return chars[len(chars) // 2] * width

    # Resample to width
    result = []
    for i in range(width):
        idx = int(i * len(values) / width)
        idx = min(idx, len(values) - 1)
        normalized = (values[idx] - min_val) / val_range
        char_idx = int(normalized * (len(chars) - 1))
        result.append(chars[char_idx])

    return "".join(result)


def print_sparkline(
    title: str,
    values: list[float],
    labels: list[str] | None = None,
) -> None:
    """Print a sparkline with optional labels.

    Args:
        title: Chart title
        values: List of numeric values
        labels: Optional labels for each value
    """
    if not values:
        return

    print_section(title)

    # Generate sparkline
    line = sparkline(values, width=min(40, len(values) * 2))
    console.print(f"  [cyan]{line}[/cyan]")

    # Print min/max
    console.print(
        f"  [dim]min: {min(values):.3f}  " f"max: {max(values):.3f}  " f"avg: {sum(values) / len(values):.3f}[/dim]"
    )

    # Print labels if provided
    if labels and len(labels) == len(values):
        console.print()
        for label, val in zip(labels, values):
            console.print(f"  [dim]{label}:[/dim] [bold]{val:.3f}[/bold]")

    console.print()


# ── Metric Comparison Table ────────────────────────────────────────────
def print_metric_comparison(
    metrics: dict[str, dict[str, Any]],
) -> None:
    """Print a formatted metric comparison table.

    Args:
        metrics: {metric_id: {name, value, status, confidence}} dict
    """
    from rich.table import Table

    table = Table(
        title="Metric Comparison",
        show_header=True,
        header_style="bold cyan",
        padding=(0, 2),
    )
    table.add_column("ID", style="bold", width=6)
    table.add_column("Metric", style="bold white")
    table.add_column("Value", justify="right", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Confidence", justify="right")

    for metric_id, info in sorted(metrics.items()):
        value = info.get("value", 0)
        status = info.get("status", "ok")
        confidence = info.get("confidence", 0)

        # Status styling
        if status == "ok":
            status_str = "[green]OK[/green]"
        elif status == "warn":
            status_str = "[yellow]WARN[/yellow]"
        else:
            status_str = "[red]ERR[/red]"

        # Confidence styling
        if confidence >= 0.8:
            conf_str = f"[green]{confidence:.2f}[/green]"
        elif confidence >= 0.5:
            conf_str = f"[yellow]{confidence:.2f}[/yellow]"
        else:
            conf_str = f"[red]{confidence:.2f}[/red]"

        table.add_row(
            metric_id,
            info.get("name", metric_id),
            f"{value:.3f}",
            status_str,
            conf_str,
        )

    console.print()
    console.print(table)
    console.print()


# ── Score Dashboard ────────────────────────────────────────────────────
def print_score_dashboard(
    integrity_score: float,
    confidence_score: float,
    detector_results: dict[str, bool] | None = None,
    metric_scores: dict[str, float] | None = None,
) -> None:
    """Print a comprehensive score dashboard with charts.

    Args:
        integrity_score: Overall integrity score (0.0-1.0)
        confidence_score: Overall confidence score (0.0-1.0)
        detector_results: {detector_id: triggered} dict
        metric_scores: {metric_id: score} dict
    """
    print_section("Score Dashboard")

    # Main scores as bar chart
    main_scores = {
        "Integrity": integrity_score,
        "Confidence": confidence_score,
    }
    print_bar_chart("Overall Scores", main_scores, width=30)

    # Detector results
    if detector_results:
        det_scores = {k: 0.0 if v else 1.0 for k, v in detector_results.items()}
        print_bar_chart("Detector Status", det_scores, width=30)

    # Metric scores
    if metric_scores:
        print_bar_chart("Metric Scores", metric_scores, width=30)

    # Verdict
    if integrity_score >= 0.9 and confidence_score >= 0.8:
        verdict = "[bold green]PASS - High integrity, high confidence[/bold green]"
    elif integrity_score >= 0.7:
        verdict = "[bold cyan]PASS - Moderate integrity[/bold cyan]"
    elif integrity_score >= 0.5:
        verdict = "[bold yellow]CAUTION - Lower integrity detected[/bold yellow]"
    else:
        verdict = "[bold red]ALERT - Significant integrity concerns[/bold red]"

    console.print(f"  [bold]Verdict:[/bold] {verdict}")
    console.print()
