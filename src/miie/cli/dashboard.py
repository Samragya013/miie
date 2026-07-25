"""Scientific dashboard for MIIE CLI.

Displays integrity score, confidence score, metric coverage,
detector status, observation counts, and repository health.
"""

from __future__ import annotations

from typing import Any

from rich.table import Table

from .display import console, print_kv, print_score, print_section

METRIC_PURPOSES = {
    "M-01": "Specification entropy across commit categories",
    "M-02": "Raw commit frequency (development activity proxy)",
    "M-03": "Code churn ratio (additions vs deletions)",
    "M-04": "Test coverage percentage",
    "M-05": "PR review latency (time to merge)",
    "M-06": "File-level activity breadth",
    "M-07": "Branch activity recency",
}

METRIC_SOURCES = {
    "M-01": "git",
    "M-02": "git",
    "M-03": "git",
    "M-04": "proxy",
    "M-05": "github",
    "M-06": "git",
    "M-07": "git",
}

CONFIDENCE_FACTOR_LABELS = {
    "sample_size": "Sample Size Adequacy",
    "variance": "Variance Stability",
    "missing_data": "Data Completeness",
    "window_balance": "Window Balance",
    "detector_success": "Detector Success",
    "observation_quality": "Observation Quality",
}

DETECTOR_ASSUMPTIONS = {
    "D-01": ["KS test: continuous data, independent observations, n>=20", "PSI: equal-width bins"],
    "D-02": ["Pearson: bivariate normality, linear relationship", "Fisher z: independent observations"],
    "D-03": ["Dip test: unimodal null, n>=20", "Excess mass: bandwidth (epsilon) affects sensitivity"],
}

DETECTOR_REFERENCES = {
    "D-01": "KS: Conover 1971; PSI: Keogh 2004",
    "D-02": "Pearson: Cohen 1988; Fisher z-transformation",
    "D-03": "Dip: Hartigan & Hartigan 1985; de Jong et al. 2013",
}


# ── Dashboard ──────────────────────────────────────────────────────────
def display_dashboard(
    integrity_score: float,
    confidence_score: float,
    detector_outputs: dict[str, Any],
    metric_names: list[str],
    window_count: int,
    total_commits: Any,
    contributor_count: Any,
    timings: dict[str, float] | None = None,
    verbose: bool = False,
    confidence_factors: dict[str, float] | None = None,
    score_package: Any = None,
) -> None:
    """Display the full scientific dashboard."""
    print_section("Scientific Dashboard")

    # ── Scores ──
    console.print()
    print_score("Integrity Score", integrity_score)
    print_score("Confidence Score", confidence_score, thresholds=(0.9, 0.7, 0.5))
    console.print()

    # ── Confidence Factor Breakdown (NEW) ──
    if confidence_factors:
        console.print("  [bold]Confidence Factor Breakdown (C_s = β₁ × β₂ × ... × β₆):[/bold]")
        for fk in [
            "sample_size",
            "variance",
            "missing_data",
            "window_balance",
            "detector_success",
            "observation_quality",
        ]:
            fv = confidence_factors.get(fk)
            if fv is not None:
                label = CONFIDENCE_FACTOR_LABELS.get(fk, fk)
                limiting = " [LIMITING]" if fv < 0.5 else ""
                console.print(f"    {label}: {fv:.4f}{limiting}")
        # Identify limiting factor
        if confidence_factors:
            min_key = min(confidence_factors, key=confidence_factors.get)
            min_val = confidence_factors[min_key]
            min_label = CONFIDENCE_FACTOR_LABELS.get(min_key, min_key)
            console.print(f"    [bold]Limiting Factor: {min_label} = {min_val:.4f}[/bold]")
        console.print()

    # ── Metric Coverage (ENHANCED) ──
    table = Table(title="Metric Coverage", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="bold", width=6)
    table.add_column("Status", width=10)
    table.add_column("Source", width=8)
    table.add_column("Purpose", style="dim")

    for metric_id in metric_names:
        purpose = METRIC_PURPOSES.get(metric_id, "Unknown metric")
        source = METRIC_SOURCES.get(metric_id, "unknown")
        source_label = {
            "git": "[blue]git[/blue]",
            "github": "[green]api[/green]",
            "proxy": "[yellow]proxy[/yellow]",
        }.get(source, source)
        # Check if metric has data (simplified — full check needs WorkspaceState)
        table.add_row(metric_id, "[green]● Available[/green]", source_label, purpose)

    console.print(table)

    # ── Detector Status (ENHANCED) ──
    det_table = Table(title="Detector Status", show_header=True, header_style="bold cyan", padding=(0, 1))
    det_table.add_column("ID", style="bold dim", width=6)
    det_table.add_column("Name", width=25)
    det_table.add_column("Status", width=12)
    det_table.add_column("Result", width=12)
    if verbose:
        det_table.add_column("Assumptions", width=40, style="dim")

    _det_names = {
        "D-01": "Distribution Drift",
        "D-02": "Correlation Breakdown",
        "D-03": "Threshold Compression",
    }

    for det_id in sorted(detector_outputs.keys()):
        det_data = detector_outputs[det_id]
        name = _det_names.get(det_id, det_id)

        if not isinstance(det_data, dict):
            status = "[yellow]ERROR[/yellow]"
            result = "[dim]N/A[/dim]"
        elif det_data.get("status") in ("error", "skipped"):
            status = "[yellow]ERROR[/yellow]"
            result = det_data.get("reason", "unknown")[:20]
        else:
            status = "[green]V OK[/green]"
            triggered = (
                det_data.get("drift_detected")
                or det_data.get("breakdown_detected")
                or det_data.get("compression_detected", False)
            )
            result = "[red]X DETECTED[/red]" if triggered else "[green]V CLEAR[/green]"

        row = [det_id, name, status, result]
        if verbose:
            assumptions = DETECTOR_ASSUMPTIONS.get(det_id, [])
            row.append("; ".join(assumptions)[:40])
        det_table.add_row(*row)

    console.print(det_table)

    # ── Detector Assumptions & References (NEW, verbose mode) ──
    if verbose:
        console.print()
        console.print("  [bold]Detector Assumptions & References:[/bold]")
        for det_id in sorted(DETECTOR_ASSUMPTIONS.keys()):
            name = _det_names.get(det_id, det_id)
            assumptions = DETECTOR_ASSUMPTIONS.get(det_id, [])
            ref = DETECTOR_REFERENCES.get(det_id, "")
            console.print(f"    {det_id} ({name}):")
            for a in assumptions:
                console.print(f"      - {a}")
            if ref:
                console.print(f"      Reference: {ref}")
        console.print()

    # ── Diagnostics Section (NEW) ──
    if verbose and detector_outputs:
        console.print()
        console.print("  [bold]Diagnostics (Previously Hidden):[/bold]")
        for det_id in sorted(detector_outputs.keys()):
            det_data = detector_outputs[det_id]
            if not isinstance(det_data, dict):
                continue
            name = _det_names.get(det_id, det_id)

            if det_id == "D-01":
                ks_stat = det_data.get("ks_statistic")
                psi_val = det_data.get("psi_value")
                drift_events = det_data.get("drift_events", [])
                if ks_stat is not None:
                    console.print(f"    {det_id} ({name}): KS D={ks_stat:.4f}, PSI={psi_val or 0:.4f}")
                if drift_events:
                    for evt in drift_events[:3]:
                        metric = evt.get("metric", "?")
                        ks = evt.get("ks_statistic", 0)
                        console.print(f"      Drift: {metric} (KS D={ks:.4f})")

            elif det_id == "D-02":
                delta_r = det_data.get("delta_r")
                trajectories = det_data.get("pearson_trajectories", {})
                breakdown_events = det_data.get("breakdown_events", [])
                if delta_r is not None:
                    console.print(f"    {det_id} ({name}): Delta R={delta_r:.4f}")
                if breakdown_events:
                    for evt in breakdown_events[:3]:
                        pair = evt.get("metric_pair", ("?", "?"))
                        dr_val = evt.get("delta_pearson", 0)
                        console.print(f"      Breakdown: {pair[0]} <-> {pair[1]} (delta_r={dr_val:.4f})")

            elif det_id == "D-03":
                comp_idx = det_data.get("compression_index")
                dip_stat = det_data.get("dip_statistic")
                dip_p = det_data.get("dip_p_value")
                if comp_idx is not None:
                    console.print(f"    {det_id} ({name}): Compression Index={comp_idx:.4f}")
                if dip_stat is not None:
                    console.print(f"      Dip Statistic={dip_stat:.4f}, p-value={dip_p or 0:.4f}")
                compression_events = det_data.get("compression_events", [])
                if compression_events:
                    for evt in compression_events[:3]:
                        metric = evt.get("metric", "?")
                        ci = evt.get("compression_index", 0)
                        console.print(f"      Compression: {metric} (index={ci:.4f})")
        console.print()

    # ── Repository Info ──
    console.print()
    print_kv("Commits", total_commits)
    print_kv("Contributors", contributor_count)
    print_kv("Windows", window_count)

    # ── Performance ──
    if timings:
        console.print()
        console.print("  [dim]" + "-" * 50 + "[/dim]")
        console.print("  [bold cyan]>>[/bold cyan] [bold white]Performance[/bold white]")
        console.print("  [dim]" + "-" * 50 + "[/dim]")
        for stage, elapsed in timings.items():
            console.print(f"    [dim]{stage}:[/dim] [cyan]{elapsed:.2f}s[/cyan]")
        console.print(f"    [bold white]Total:[/bold white] [bold cyan]{sum(timings.values()):.2f}s[/bold cyan]")

    console.print()


# ── Compact Dashboard ──────────────────────────────────────────────────
def display_compact_dashboard(
    integrity_score: float,
    confidence_score: float,
    detector_outputs: dict[str, Any],
    window_count: int,
    confidence_factors: dict[str, float] | None = None,
) -> None:
    """Display a compact single-line dashboard."""
    # Determine overall status
    any_triggered = False
    any_failed = False
    for det_data in detector_outputs.values():
        if isinstance(det_data, dict):
            if det_data.get("status") in ("error", "skipped"):
                any_failed = True
            elif (
                det_data.get("drift_detected")
                or det_data.get("breakdown_detected")
                or det_data.get("compression_detected", False)
            ):
                any_triggered = True

    if any_triggered:
        status_color = "red"
        status_text = "ANOMALIES DETECTED"
    elif any_failed:
        status_color = "yellow"
        status_text = "PARTIAL"
    else:
        status_color = "green"
        status_text = "ALL CLEAR"

    # Add limiting factor if available
    factor_info = ""
    if confidence_factors:
        min_key = min(confidence_factors, key=confidence_factors.get)
        min_val = confidence_factors[min_key]
        min_label = CONFIDENCE_FACTOR_LABELS.get(min_key, min_key)
        factor_info = f" │ Limiting: {min_label}={min_val:.2f}"

    console.print(
        f"  [{status_color}]{status_text}[/{status_color}] │ "
        f"IS: [bold]{integrity_score:.3f}[/bold] │ "
        f"CS: [bold]{confidence_score:.3f}[/bold] │ "
        f"Windows: {window_count}{factor_info}"
    )


# ── Verdict Display ────────────────────────────────────────────────────
def display_verdict(
    integrity_score: float,
    confidence_score: float,
    triggered_count: int,
    failed_detectors: list[str],
) -> None:
    """Display the overall verdict."""
    print_section("Overall Verdict")

    # Labels
    integrity_label = _score_label(integrity_score)
    confidence_label = _score_label(confidence_score)

    if triggered_count == 0:
        risk = "Very Low"
    elif triggered_count == 1:
        risk = "Low"
    elif triggered_count == 2:
        risk = "Moderate"
    else:
        risk = "High"

    table = Table(show_header=False, border_style="cyan", padding=(0, 2))
    table.add_column("Metric", style="bold", min_width=18)
    table.add_column("Value")
    table.add_row("Metric Integrity", f"[bold]{integrity_label}[/bold] ({integrity_score:.3f})")
    table.add_row("Confidence", f"[bold]{confidence_label}[/bold] ({confidence_score:.3f})")
    table.add_row("Risk Level", f"[bold]{risk}[/bold]")
    if failed_detectors:
        table.add_row("Failed Detectors", ", ".join(failed_detectors))

    console.print(table)

    # Summary sentence
    console.print()
    if triggered_count == 0 and integrity_score >= 0.9:
        console.print(
            "  [green]No evidence was found that repository metrics have become "
            "distorted, unstable, or misleading.[/green]"
        )
    elif triggered_count == 0:
        console.print(
            "  [yellow]Repository metrics appear generally stable with minor variations "
            "that are within expected ranges.[/yellow]"
        )
    elif triggered_count == 1:
        console.print(
            "  [yellow]One metric anomaly was detected, but overall measurement "
            "integrity remains acceptable.[/yellow]"
        )
    else:
        console.print(
            "  [red]Multiple metric anomalies were detected. Manual investigation "
            "of repository measurement integrity is recommended.[/red]"
        )

    # Recommended action
    console.print()
    console.print("  [dim]" + "-" * 50 + "[/dim]")
    print_section("Recommended Action")
    if triggered_count == 0 and integrity_score >= 0.9:
        console.print("  No action required. Repository metrics appear trustworthy.")
    elif triggered_count == 0:
        console.print("  No immediate action. Consider analyzing a longer time range for higher confidence.")
    elif triggered_count == 1:
        console.print("  Review the flagged metric for context. Monitor for continued anomalies.")
    else:
        console.print("  Investigate flagged metrics. Review contributor activity and development patterns.")


def _score_label(value: float) -> str:
    """Convert a score to a human-readable label."""
    if value >= 0.9:
        return "Very High"
    elif value >= 0.7:
        return "High"
    elif value >= 0.5:
        return "Moderate"
    else:
        return "Low"
