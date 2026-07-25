"""Workspace Views — Deterministic renderers for each workspace section.

Every view is a pure function: same inputs → same output.
Views read ONLY from workspace state (frozen scientific core outputs).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .engine import WorkspaceEngine


@dataclass
class ViewResult:
    """A rendered view section."""

    title: str
    lines: List[str]
    actions: List[str]
    bookmarks: List[str]


class ExecutiveSummary:
    """Executive summary view — all key findings in one view."""

    METRIC_PURPOSES = {
        "M-01": "Entropy Ratio — measures specification entropy across categories",
        "M-02": "Commit Count — raw commit frequency",
        "M-03": "Churn Ratio — additions/deletions ratio (requires file-level data)",
        "M-04": "Test Coverage — test coverage percentage (requires CI integration)",
        "M-05": "Review Latency — PR review time (requires PR API)",
        "M-06": "File Change Count — file-level activity breadth",
        "M-07": "Branch Freshness — branch activity recency (requires branch data)",
    }

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        """Render executive summary."""
        state = workspace.state
        lines = []
        actions = []
        bookmarks = []

        lines.append("=" * 72)
        lines.append("EXECUTIVE SUMMARY")
        lines.append("=" * 72)
        lines.append("")

        # Repository identity
        lines.append("Repository: " + (state.repo_path or "Unknown"))
        lines.append("Repository ID: " + (state.repo_id or "Unknown"))
        lines.append("Analysis Completed: " + state.created_at)
        lines.append("")

        # Key scores
        sp = state.score_package
        if sp is not None:
            integrity = getattr(sp, "integrity", None)
            confidence = getattr(sp, "confidence", None)

            if integrity is not None:
                score = getattr(integrity, "overall", 0.0) or 0.0
                lines.append(f"Integrity Score: {score:.3f}")
                risk = self._risk_level(score)
                lines.append(f"Risk Level: {risk}")

            if confidence is not None:
                score = getattr(confidence, "overall", 0.0) or 0.0
                band = getattr(confidence, "band", "unknown") or "unknown"
                lines.append(f"Confidence Score: {score:.3f} (band: {band})")

                # Confidence factor breakdown
                factors = getattr(confidence, "factors", {}) or {}
                if factors:
                    lines.append("  Confidence Factors:")
                    factor_labels = {
                        "sample_size": "Sample Size Adequacy",
                        "variance": "Variance Stability",
                        "missing_data": "Data Completeness",
                        "window_balance": "Window Balance",
                        "detector_success": "Detector Success",
                        "observation_quality": "Observation Quality",
                    }
                    for fk, fv in factors.items():
                        label = factor_labels.get(fk, fk)
                        lines.append(f"    {label}: {fv:.4f}")

        lines.append("")

        # Verdict
        er = state.explanation_report
        if er is not None:
            verdict = getattr(er, "verdict", None)
            if verdict:
                lines.append(f"Verdict: {verdict.value if hasattr(verdict, 'value') else verdict}")

        lines.append("")

        # Detector overview
        dr = state.detector_results
        if dr is not None:
            detector_outputs = getattr(dr, "detector_outputs", {}) or {}
            if detector_outputs:
                lines.append("Detector Overview:")
                det_names = {
                    "D-01": "Distribution Drift",
                    "D-02": "Correlation Breakdown",
                    "D-03": "Threshold Compression",
                }
                for det_id in sorted(detector_outputs.keys()):
                    det_data = detector_outputs[det_id]
                    name = det_names.get(det_id, det_id)
                    if isinstance(det_data, dict):
                        triggered = (
                            det_data.get("drift_detected")
                            or det_data.get("breakdown_detected")
                            or det_data.get("compression_detected", False)
                        )
                        status = "DETECTED" if triggered else "CLEAR"
                        lines.append(f"  {det_id} ({name}): {status}")
                    else:
                        lines.append(f"  {det_id} ({name}): UNKNOWN")
        lines.append("")

        # Metric status
        metrics = state.metrics_analyzed
        if metrics:
            lines.append("Metric Status:")
            for mid in metrics:
                purpose = self.METRIC_PURPOSES.get(mid, "Unknown metric")
                lines.append(f"  {mid}: {purpose}")
        lines.append("")

        # Evidence sufficiency
        ep = state.evidence_package
        if ep is not None:
            obs_summary = getattr(ep, "observation_summary", None)
            if obs_summary is not None:
                total = obs_summary.get("total_observations", 0) if isinstance(obs_summary, dict) else 0
                quality = obs_summary.get("observation_quality", {}) if isinstance(obs_summary, dict) else {}
                complete = quality.get("complete", 0)
                lines.append(f"Evidence: {total} observations ({complete} complete)")

            # Statistical artifacts summary
            artifacts = getattr(ep, "statistical_artifacts", None)
            if artifacts and isinstance(artifacts, dict):
                drift_stats = artifacts.get("drift_statistics", {})
                corr_arts = artifacts.get("correlation_artifacts", {})
                comp_arts = artifacts.get("compression_artifacts", {})
                art_count = sum(len(v) for v in [drift_stats, corr_arts, comp_arts] if v)
                if art_count:
                    lines.append(f"Statistical Artifacts: {art_count} categories available")
        lines.append("")

        # Validation status
        if ep is not None:
            vm = getattr(ep, "validation_metrics", None)
            if vm:
                total = vm.get("total_observations", 0)
                valid = vm.get("valid_observations", 0)
                lines.append(f"Validation: {valid}/{total} observations valid")

        lines.append("")

        # Benchmark status
        bench = getattr(state, "benchmark", None)
        if bench is not None:
            lines.append("Benchmark: Completed")
        else:
            lines.append("Benchmark: Not run")

        lines.append("")

        # Recommendations count
        if er is not None:
            recs = getattr(er, "recommendations", []) or []
            lines.append(f"Recommendations: {len(recs)}")

        lines.append("")

        # Actions
        actions.extend(
            [
                "1. Explore Metrics",
                "2. Explore Detectors",
                "3. Explore Evidence",
                "4. Explore Confidence",
                "5. Explore Integrity",
                "6. View Diagnostics",
                "7. View Assurance",
                "8. View Traceability",
                "9. View Recommendations",
                "10. Export Results",
            ]
        )

        # Bookmarks
        bookmarks.append("Add Bookmark: Save current view")

        return ViewResult(
            title="Executive Summary",
            lines=lines,
            actions=actions,
            bookmarks=bookmarks,
        )

    def _risk_level(self, score: float) -> str:
        if score >= 0.8:
            return "LOW"
        elif score >= 0.5:
            return "MEDIUM"
        elif score >= 0.2:
            return "HIGH"
        return "CRITICAL"


class ExplorationView:
    """Base class for exploration views."""

    def _safe_get(self, obj: Any, attr: str, default: Any = None) -> Any:
        """Safely get attribute."""
        if obj is None:
            return default
        return getattr(obj, attr, default)


class MetricView(ExplorationView):
    """Metrics exploration view."""

    METRIC_INFO = {
        "M-01": {
            "name": "Entropy Ratio",
            "purpose": "Measures specification entropy across categories",
            "method": "Shannon entropy on conventional commit categories",
            "data_source": "Git commit messages (conventional commits)",
            "available": True,
        },
        "M-02": {
            "name": "Commit Count",
            "purpose": "Raw commit frequency as development activity proxy",
            "method": "Count of commits per window",
            "data_source": "Git commit history",
            "available": True,
        },
        "M-03": {
            "name": "Churn Ratio",
            "purpose": "Ratio of code additions to deletions",
            "method": "additions / (additions + deletions) per file",
            "data_source": "Requires --numstat git output (file-level diffs)",
            "available": False,
        },
        "M-04": {
            "name": "Test Coverage",
            "purpose": "Percentage of code covered by tests",
            "method": "Coverage report integration (Cobertura/JaCoCo/coverage.py)",
            "data_source": "Requires CI/CD coverage report ingestion",
            "available": False,
        },
        "M-05": {
            "name": "Review Latency",
            "purpose": "Time between PR creation and merge",
            "method": "Median merge time per window",
            "data_source": "Requires GitHub/GitLab PR API integration",
            "available": False,
        },
        "M-06": {
            "name": "File Change Count",
            "purpose": "Breadth of file-level activity",
            "method": "Count of distinct files changed per window",
            "data_source": "Git commit file lists",
            "available": True,
        },
        "M-07": {
            "name": "Branch Freshness",
            "purpose": "Recency of branch activity",
            "method": "Days since last commit on each branch",
            "data_source": "Requires git branch metadata extraction",
            "available": False,
        },
    }

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        state = workspace.state
        lines = []
        actions = []

        lines.append("=" * 72)
        lines.append("METRICS ANALYSIS")
        lines.append("=" * 72)
        lines.append("")

        df = state.metric_dataframe
        metrics = state.metrics_analyzed

        lines.append(f"Metrics Configured: {len(metrics)}")
        lines.append("")

        for mid in metrics:
            info = self.METRIC_INFO.get(
                mid,
                {"name": mid, "purpose": "Unknown", "method": "Unknown", "data_source": "Unknown", "available": False},
            )
            lines.append(f"  {mid} — {info['name']}")
            lines.append(f"    Purpose: {info['purpose']}")
            lines.append(f"    Method: {info['method']}")
            lines.append(f"    Data Source: {info['data_source']}")

            # Check if metric has data
            if df is not None and hasattr(df, "metrics") and isinstance(df.metrics, dict):
                metric_data = df.metrics.get(mid)
                if metric_data and isinstance(metric_data, dict):
                    # Aggregate values across windows
                    all_values = []
                    for window_key, value_list in metric_data.items():
                        if isinstance(value_list, list):
                            all_values.extend([v for v in value_list if v is not None])
                    if all_values:
                        mean_val = sum(all_values) / len(all_values)
                        min_val = min(all_values)
                        max_val = max(all_values)
                        lines.append(f"    Status: COMPUTED ({len(all_values)} observations)")
                        lines.append(f"    Value: mean={mean_val:.4f}, range=[{min_val:.4f}, {max_val:.4f}]")
                    else:
                        lines.append(f"    Status: NO DATA (configured but no observations)")
                else:
                    lines.append(f"    Status: NOT COMPUTED")
            elif df is not None and hasattr(df, "metrics") and isinstance(df.metrics, list) and mid in df.metrics:
                lines.append(f"    Status: CONFIGURED (column present)")
            else:
                if info["available"]:
                    lines.append(f"    Status: NOT COMPUTED (data source available)")
                else:
                    lines.append(f"    Status: NOT AVAILABLE (requires external data source)")
            lines.append("")

        # Per-metric integrity scores
        sp = state.score_package
        if sp is not None:
            integrity = getattr(sp, "integrity", None)
            if integrity is not None:
                per_metric = getattr(integrity, "per_metric", {}) or {}
                if per_metric:
                    lines.append("Per-Metric Integrity Scores:")
                    for mid in metrics:
                        score = per_metric.get(mid)
                        if score is not None:
                            lines.append(f"  {mid}: {score:.4f}")
                        else:
                            lines.append(f"  {mid}: N/A")
                    lines.append("")

        actions.append("Select a metric for detailed view")
        actions.append("View per-metric integrity scores")

        return ViewResult("Metrics", lines, actions, [])


class DetectorView(ExplorationView):
    """Detectors exploration view."""

    DETECTOR_INFO = {
        "D-01": {
            "name": "Distribution Drift",
            "method": "Kolmogorov-Smirnov two-sample test + PSI",
            "assumptions": [
                "Continuous or ordinal metric values",
                "Independent observations within windows",
                "Sufficient sample size (>= 20 per window)",
            ],
            "limitations": [
                "Sensitive to sample size — large n can detect trivially small drifts",
                "Does not identify cause of drift",
                "PSI assumes equal-width bins",
            ],
            "reference": "KS test: Conover 1971; PSI: Keogh 2004",
        },
        "D-02": {
            "name": "Correlation Breakdown",
            "method": "Pearson correlation with Fisher z-transformation",
            "assumptions": [
                "Bivariate normality of metric pairs",
                "Linear relationship between metrics",
                "Independent observations",
            ],
            "limitations": [
                "Pearson detects only linear associations",
                "Sensitive to outliers",
                "Does not detect non-monotonic relationships",
            ],
            "reference": "Cohen 1988; Fisher z-transformation",
        },
        "D-03": {
            "name": "Threshold Compression",
            "method": "Dip test for unimodality + excess mass analysis",
            "assumptions": [
                "Unimodal null distribution",
                "Sufficient sample size (>= 20)",
                "Continuous metric values",
            ],
            "limitations": [
                "Dip test has reduced power for small samples",
                "Excess mass bandwidth (epsilon) affects sensitivity",
                "Does not identify optimal threshold location",
            ],
            "reference": "Hartigan & Hartigan 1985; de Jong et al. 2013",
        },
    }

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        state = workspace.state
        lines = []
        actions = []

        lines.append("=" * 72)
        lines.append("DETECTOR RESULTS")
        lines.append("=" * 72)
        lines.append("")

        dr = state.detector_results
        if dr is None:
            lines.append("No detector results available.")
            return ViewResult("Detectors", lines, actions, [])

        detector_outputs = getattr(dr, "detector_outputs", {}) or {}
        lines.append(f"Detectors Executed: {len(detector_outputs)}")
        lines.append("")

        for det_id in sorted(detector_outputs.keys()):
            det_data = detector_outputs[det_id]
            info = self.DETECTOR_INFO.get(
                det_id, {"name": det_id, "method": "Unknown", "assumptions": [], "limitations": [], "reference": ""}
            )

            lines.append(f"  {det_id}: {info['name']}")
            lines.append(f"    Method: {info['method']}")

            if isinstance(det_data, dict):
                # Status
                status = det_data.get("status", "executed")
                if status in ("error", "skipped"):
                    lines.append(f"    Status: {status.upper()} — {det_data.get('reason', 'unknown')}")
                else:
                    # Trigger status
                    triggered = (
                        det_data.get("drift_detected")
                        or det_data.get("breakdown_detected")
                        or det_data.get("compression_detected", False)
                    )
                    lines.append(f"    Status: {'DETECTED' if triggered else 'CLEAR'}")

                    # Key statistics
                    if det_id == "D-01":
                        ks_stat = det_data.get("ks_statistic")
                        psi_val = det_data.get("psi_value")
                        if ks_stat is not None:
                            lines.append(f"    KS Statistic: {ks_stat:.4f}")
                        if psi_val is not None:
                            lines.append(f"    PSI Value: {psi_val:.4f}")

                        # Per-window details
                        window_pairs = det_data.get("window_pairs_analyzed", [])
                        if window_pairs:
                            lines.append(f"    Window Pairs Analyzed: {len(window_pairs)}")

                        # Drift events
                        drift_events = det_data.get("drift_events", [])
                        if drift_events:
                            lines.append(f"    Drift Events: {len(drift_events)}")
                            for evt in drift_events[:3]:
                                metric = evt.get("metric", "unknown")
                                ks = evt.get("ks_statistic", 0)
                                lines.append(f"      {metric}: KS D={ks:.4f}")

                    elif det_id == "D-02":
                        breakdown = det_data.get("breakdown_detected", False)
                        delta_r = det_data.get("delta_r")
                        if delta_r is not None:
                            lines.append(f"    Delta R: {delta_r:.4f}")

                        # Pearson trajectories
                        trajectories = det_data.get("pearson_trajectories", {})
                        if trajectories:
                            lines.append(f"    Metric Pairs Analyzed: {len(trajectories)}")

                        # Breakdown events
                        events = det_data.get("breakdown_events", [])
                        if events:
                            lines.append(f"    Breakdown Events: {len(events)}")
                            for evt in events[:3]:
                                pair = evt.get("metric_pair", ("?", "?"))
                                dr_val = evt.get("delta_pearson", 0)
                                lines.append(f"      {pair[0]} <-> {pair[1]}: delta_r={dr_val:.4f}")

                    elif det_id == "D-03":
                        comp_idx = det_data.get("compression_index")
                        dip_stat = det_data.get("dip_statistic")
                        dip_p = det_data.get("dip_p_value")
                        if comp_idx is not None:
                            lines.append(f"    Compression Index: {comp_idx:.4f}")
                        if dip_stat is not None:
                            lines.append(f"    Dip Statistic: {dip_stat:.4f}")
                        if dip_p is not None:
                            lines.append(f"    Dip p-value: {dip_p:.4f}")

                        # Compression events
                        events = det_data.get("compression_events", [])
                        if events:
                            lines.append(f"    Compression Events: {len(events)}")
                            for evt in events[:3]:
                                metric = evt.get("metric", "unknown")
                                ci = evt.get("compression_index", 0)
                                lines.append(f"      {metric}: index={ci:.4f}")

            # Assumptions
            if info["assumptions"]:
                lines.append(f"    Assumptions:")
                for a in info["assumptions"]:
                    lines.append(f"      - {a}")

            # Limitations
            if info["limitations"]:
                lines.append(f"    Limitations:")
                for l in info["limitations"]:
                    lines.append(f"      - {l}")

            # Reference
            if info["reference"]:
                lines.append(f"    Reference: {info['reference']}")

            lines.append("")

        actions.append("Select a detector for detailed view")
        actions.append("View per-detector severity breakdown")

        return ViewResult("Detectors", lines, actions, [])


class EvidenceView(ExplorationView):
    """Evidence exploration view."""

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        state = workspace.state
        lines = []
        actions = []

        lines.append("=" * 72)
        lines.append("EVIDENCE ANALYSIS")
        lines.append("=" * 72)
        lines.append("")

        ep = state.evidence_package
        if ep is None:
            lines.append("No evidence package available.")
            return ViewResult("Evidence", lines, actions, [])

        # Provenance
        provenance = getattr(ep, "provenance", None)
        if provenance is not None:
            created = getattr(provenance, "created_at", "unknown")
            lines.append(f"Evidence Generated: {created}")
        lines.append("")

        # Observation summary (dict-based)
        obs_summary = getattr(ep, "observation_summary", None) or {}
        if isinstance(obs_summary, dict) and obs_summary:
            total = obs_summary.get("total_observations", 0)
            per_metric = obs_summary.get("per_metric", {})
            quality = obs_summary.get("observation_quality", {})

            lines.append(f"Total Observations: {total}")
            if quality:
                complete = quality.get("complete", 0)
                partial = quality.get("partial", 0)
                estimated = quality.get("estimated", 0)
                lines.append(f"  Complete: {complete}")
                lines.append(f"  Partial: {partial}")
                lines.append(f"  Estimated: {estimated}")
            lines.append("")

            if per_metric:
                lines.append("Per-Metric Observations:")
                for mid, mdata in sorted(per_metric.items()):
                    count = mdata.get("count", 0) if isinstance(mdata, dict) else 0
                    wc = mdata.get("window_count", 0) if isinstance(mdata, dict) else 0
                    vr = mdata.get("value_range", [None, None]) if isinstance(mdata, dict) else [None, None]
                    range_str = f"[{vr[0]:.4f}, {vr[1]:.4f}]" if all(v is not None for v in vr) else "N/A"
                    lines.append(f"  {mid}: {count} obs, {wc} windows, range={range_str}")
                lines.append("")

        # Detector execution metadata
        det_meta = getattr(ep, "detector_execution_metadata", None) or {}
        if det_meta:
            lines.append("Detector Execution Metadata:")
            for det_id, meta in sorted(det_meta.items()):
                if isinstance(meta, dict):
                    method = meta.get("method", "unknown")
                    exec_time = meta.get("execution_time_seconds", 0)
                    windows_analyzed = meta.get("windows_analyzed", 0)
                    observations = meta.get("observations_consumed", 0)
                    ref = meta.get("scientific_reference", "")
                    lines.append(f"  {det_id}:")
                    lines.append(f"    Method: {method}")
                    lines.append(f"    Execution Time: {exec_time:.3f}s")
                    lines.append(f"    Windows Analyzed: {windows_analyzed}")
                    lines.append(f"    Observations Consumed: {observations}")
                    if ref:
                        lines.append(f"    Reference: {ref}")
            lines.append("")

        # Statistical artifacts (currently hidden)
        artifacts = getattr(ep, "statistical_artifacts", None) or {}
        if artifacts:
            lines.append("Statistical Artifacts:")
            drift = artifacts.get("drift_statistics", {})
            corr = artifacts.get("correlation_artifacts", {})
            comp = artifacts.get("compression_artifacts", {})
            if drift:
                lines.append(f"  Drift Statistics: {len(drift)} detector(s)")
            if corr:
                lines.append(f"  Correlation Artifacts: {len(corr)} detector(s)")
            if comp:
                lines.append(f"  Compression Artifacts: {len(comp)} detector(s)")
            lines.append("")

        # Warnings
        warnings = getattr(ep, "warnings", []) or []
        if warnings:
            lines.append(f"Warnings: {len(warnings)}")
            for w in warnings[:5]:
                msg = getattr(w, "message", str(w))
                lines.append(f"  - {msg}")
            lines.append("")

        # Metrics summary
        metrics = getattr(ep, "metrics", {}) or {}
        if metrics:
            lines.append(f"Metrics Summary: {len(metrics)} entries")
        lines.append("")

        actions.append("Select a metric for evidence detail")
        actions.append("View evidence provenance")
        actions.append("View statistical artifacts")

        return ViewResult("Evidence", lines, actions, [])


class ConfidenceView(ExplorationView):
    """Confidence exploration view."""

    FACTOR_LABELS = {
        "sample_size": ("Sample Size Adequacy", "min(1, mean_n / 50)"),
        "variance": ("Variance Stability", "1 - min(1, mean_CV / 0.5)"),
        "missing_data": ("Data Completeness", "1 - (missing_pairs / total_pairs)"),
        "window_balance": ("Window Balance", "1 - min(1, std_size / mean_size)"),
        "detector_success": ("Detector Success", "successful_runs / total_attempts"),
        "observation_quality": ("Observation Quality", "(complete + 0.5*partial) / total"),
    }

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        state = workspace.state
        lines = []
        actions = []

        lines.append("=" * 72)
        lines.append("CONFIDENCE ANALYSIS")
        lines.append("=" * 72)
        lines.append("")

        sp = state.score_package
        if sp is None:
            lines.append("No score package available.")
            return ViewResult("Confidence", lines, actions, [])

        confidence = getattr(sp, "confidence", None)
        if confidence is None:
            lines.append("No confidence score available.")
            return ViewResult("Confidence", lines, actions, [])

        # Overall confidence score
        score = getattr(confidence, "overall", 0.0) or 0.0
        band = getattr(confidence, "band", "unknown") or "unknown"
        level = getattr(confidence, "level", "unknown") or "unknown"
        lines.append(f"Overall Confidence: {score:.4f}")
        lines.append(f"Band: {band}")
        lines.append(f"Level: {level}")
        lines.append(f"Formula: C_s = product(beta_i) for i in 1..6")
        lines.append("")

        # Factor breakdown
        factors = getattr(confidence, "factors", {}) or {}
        if factors:
            lines.append("Confidence Factor Breakdown (C_s = beta_1 * beta_2 * ... * beta_6):")
            lines.append("")
            for fk in [
                "sample_size",
                "variance",
                "missing_data",
                "window_balance",
                "detector_success",
                "observation_quality",
            ]:
                fv = factors.get(fk)
                if fv is not None:
                    label, formula = self.FACTOR_LABELS.get(fk, (fk, ""))
                    limiting = " [LIMITING]" if fv < 0.5 else ""
                    lines.append(f"  beta_{fk}: {fv:.4f} — {label}{limiting}")
                    if formula:
                        lines.append(f"    Formula: {formula}")
            lines.append("")

            # Identify limiting factor
            min_factor = min(factors.values()) if factors else 0
            min_key = min(factors, key=factors.get) if factors else "none"
            lines.append(f"  Limiting Factor: {min_key} = {min_factor:.4f}")
            lines.append(
                f"  Interpretation: Confidence is {'limited' if min_factor < 0.5 else 'supported'} by {min_key}"
            )
        lines.append("")

        # Confidence interpretation
        if score >= 0.8:
            interp = "HIGH confidence — results are statistically well-supported"
        elif score >= 0.5:
            interp = "MEDIUM confidence — results are moderately supported"
        else:
            interp = "LOW confidence — results have limited statistical support"
        lines.append(f"Interpretation: {interp}")

        lines.append("")
        actions.append("View factor definitions")
        actions.append("View confidence traceability")

        return ViewResult("Confidence", lines, actions, [])


class IntegrityView(ExplorationView):
    """Integrity exploration view."""

    SEVERITY_LABELS = {
        0.0: ("LOW", "Minor integrity concern"),
        0.3: ("MEDIUM", "Moderate integrity concern"),
        0.6: ("HIGH", "Significant integrity concern"),
        0.8: ("CRITICAL", "Major integrity concern"),
    }

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        state = workspace.state
        lines = []
        actions = []

        lines.append("=" * 72)
        lines.append("INTEGRITY ANALYSIS")
        lines.append("=" * 72)
        lines.append("")

        sp = state.score_package
        if sp is None:
            lines.append("No score package available.")
            return ViewResult("Integrity", lines, actions, [])

        integrity = getattr(sp, "integrity", None)
        if integrity is None:
            lines.append("No integrity score available.")
            return ViewResult("Integrity", lines, actions, [])

        # Overall integrity score
        overall = getattr(integrity, "overall", 0.0) or 0.0
        formula_version = getattr(integrity, "formula_version", "unknown") or "unknown"
        lines.append(f"Overall Integrity Score: {overall:.4f}")
        lines.append(f"Formula Version: {formula_version}")
        lines.append("")

        # Severity classification
        if overall >= 0.8:
            sev = "LOW (high integrity)"
        elif overall >= 0.6:
            sev = "MEDIUM (moderate integrity)"
        elif overall >= 0.3:
            sev = "HIGH (low integrity)"
        else:
            sev = "CRITICAL (very low integrity)"
        lines.append(f"Severity Classification: {sev}")
        lines.append("")

        # Per-metric integrity scores
        per_metric = getattr(integrity, "per_metric", {}) or {}
        if per_metric:
            lines.append("Per-Metric Integrity Scores:")
            for metric_id, score in sorted(per_metric.items()):
                if score < 0.3:
                    indicator = "[!!!]"
                elif score < 0.6:
                    indicator = "[!! ]"
                elif score < 0.8:
                    indicator = "[!  ]"
                else:
                    indicator = "[   ]"
                lines.append(f"  {indicator} {metric_id}: {score:.4f}")
            lines.append("")
            lines.append("  Legend: [!!!] critical, [!! ] high, [!  ] medium, [   ] low")
        lines.append("")

        # Interpretation
        lines.append("Interpretation:")
        lines.append("  IS = weighted sum of per-metric scores, each derived from")
        lines.append("  detector results. The severity multiplier s = 1.0 - IS is")
        lines.append("  applied to adjust confidence downward for low-integrity results.")
        lines.append("")

        # Per-metric details from detector outputs
        dr = state.detector_results
        if dr is not None and per_metric:
            detector_outputs = getattr(dr, "detector_outputs", {}) or {}
            lines.append("Per-Metric Breakdown:")
            for metric_id, score in sorted(per_metric.items()):
                lines.append(f"  {metric_id} (integrity={score:.4f}):")
                # Find which detectors flagged this metric
                for det_id, det_data in detector_outputs.items():
                    if isinstance(det_data, dict):
                        # D-01 drift events
                        drift_events = det_data.get("drift_events", [])
                        for evt in drift_events:
                            if evt.get("metric") == metric_id:
                                ks = evt.get("ks_statistic", 0)
                                lines.append(f"    {det_id}: drift detected (KS D={ks:.4f})")
                        # D-02 breakdown events
                        breakdown_events = det_data.get("breakdown_events", [])
                        for evt in breakdown_events:
                            if metric_id in (evt.get("metric_pair", ())):
                                dr_val = evt.get("delta_pearson", 0)
                                lines.append(f"    {det_id}: correlation breakdown (delta_r={dr_val:.4f})")
                        # D-03 compression events
                        compression_events = det_data.get("compression_events", [])
                        for evt in compression_events:
                            if evt.get("metric") == metric_id:
                                ci = evt.get("compression_index", 0)
                                lines.append(f"    {det_id}: threshold compression (index={ci:.4f})")
                lines.append("")

        actions.append("Select a metric for integrity detail")
        actions.append("View finding details")

        return ViewResult("Integrity", lines, actions, [])


class ValidationView(ExplorationView):
    """Validation exploration view."""

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        state = workspace.state
        lines = []
        actions = []

        lines.append("=" * 72)
        lines.append("VALIDATION STATUS")
        lines.append("=" * 72)
        lines.append("")

        ep = state.evidence_package
        if ep is None:
            lines.append("No evidence package available.")
            return ViewResult("Validation", lines, actions, [])

        # Observation summary (dict-based)
        obs_summary = getattr(ep, "observation_summary", None) or {}
        if isinstance(obs_summary, dict) and obs_summary:
            total = obs_summary.get("total_observations", 0)
            quality = obs_summary.get("observation_quality", {})
            complete = quality.get("complete", 0) if isinstance(quality, dict) else 0
            partial = quality.get("partial", 0) if isinstance(quality, dict) else 0
            estimated = quality.get("estimated", 0) if isinstance(quality, dict) else 0
            invalid = total - complete - partial - estimated

            lines.append(f"Total Observations: {total}")
            lines.append(f"  Complete: {complete}")
            lines.append(f"  Partial: {partial}")
            lines.append(f"  Estimated: {estimated}")
            lines.append(f"  Invalid: {invalid}")
            lines.append("")

            # Quality score
            if total > 0:
                quality_score = (complete + 0.5 * partial) / total
                lines.append(f"Quality Score: {quality_score:.4f}")
                if quality_score >= 0.8:
                    lines.append("Quality Level: HIGH")
                elif quality_score >= 0.5:
                    lines.append("Quality Level: MEDIUM")
                else:
                    lines.append("Quality Level: LOW")
        else:
            # Fallback to validation_metrics
            vm = getattr(ep, "validation_metrics", None)
            if vm:
                total = vm.get("total_observations", 0)
                valid = vm.get("valid_observations", 0)
                invalid = vm.get("invalid_observations", 0)
                lines.append(f"Total Observations: {total}")
                lines.append(f"Valid: {valid}")
                lines.append(f"Invalid: {invalid}")
            else:
                lines.append("No validation metrics available.")
        lines.append("")

        # Per-metric validation
        per_metric = obs_summary.get("per_metric", {}) if isinstance(obs_summary, dict) else {}
        if per_metric:
            lines.append("Per-Metric Validation:")
            for mid, mdata in sorted(per_metric.items()):
                if isinstance(mdata, dict):
                    count = mdata.get("count", 0)
                    wc = mdata.get("window_count", 0)
                    vr = mdata.get("value_range", [None, None])
                    range_str = f"[{vr[0]:.4f}, {vr[1]:.4f}]" if all(v is not None for v in vr) else "N/A"
                    lines.append(f"  {mid}: {count} obs, {wc} windows, range={range_str}")
            lines.append("")

        # Detector execution metadata
        det_meta = getattr(ep, "detector_execution_metadata", None) or {}
        if det_meta:
            lines.append("Detector Execution Summary:")
            for det_id, meta in sorted(det_meta.items()):
                if isinstance(meta, dict):
                    method = meta.get("method", "unknown")
                    windows = meta.get("windows_analyzed", 0)
                    observations = meta.get("observations_consumed", 0)
                    lines.append(f"  {det_id}: {method} — {windows} windows, {observations} obs")
            lines.append("")

        actions.append("View validation details by metric")

        return ViewResult("Validation", lines, actions, [])


class DiagnosticsView(ExplorationView):
    """Diagnostics view — effect sizes, power, MDE, CI widths."""

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        state = workspace.state
        lines = []
        actions = []

        lines.append("=" * 72)
        lines.append("DIAGNOSTICS (Previously Hidden)")
        lines.append("=" * 72)
        lines.append("")

        ep = state.evidence_package
        if ep is None:
            lines.append("No evidence package available.")
            return ViewResult("Diagnostics", lines, actions, [])

        artifacts = getattr(ep, "statistical_artifacts", None) or {}
        det_meta = getattr(ep, "detector_execution_metadata", None) or {}
        det_results = state.detector_results
        detector_outputs = getattr(det_results, "detector_outputs", {}) if det_results else {}

        # D-01 Effect Sizes (Cohen's d, KS effect size, rank biserial)
        lines.append("D-01 Distribution Drift — Effect Sizes:")
        lines.append("")
        drift_stats = artifacts.get("drift_statistics", {})
        if drift_stats:
            for det_id, ddata in drift_stats.items():
                if isinstance(ddata, dict):
                    ks_stats = ddata.get("ks_statistics", {})
                    psi_vals = ddata.get("psi_values", {})
                    if ks_stats:
                        lines.append("  KS Statistics by Metric Pair:")
                        for pair, val in ks_stats.items():
                            lines.append(f"    {pair}: D = {val:.4f}")
                    if psi_vals:
                        lines.append("  PSI Values by Metric Pair:")
                        for pair, val in psi_vals.items():
                            lines.append(f"    {pair}: PSI = {val:.4f}")
        else:
            # Try to extract from detector_outputs
            d01 = detector_outputs.get("D-01", {})
            if isinstance(d01, dict):
                ks_stat = d01.get("ks_statistic")
                psi_val = d01.get("psi_value")
                if ks_stat is not None:
                    lines.append(f"  Aggregate KS Statistic: {ks_stat:.4f}")
                if psi_val is not None:
                    lines.append(f"  Aggregate PSI Value: {psi_val:.4f}")
        lines.append("")

        # D-02 Correlation Artifacts (Pearson trajectories, Fisher z, confidence intervals)
        lines.append("D-02 Correlation Breakdown — Trajectories:")
        lines.append("")
        corr_arts = artifacts.get("correlation_artifacts", {})
        if corr_arts:
            for det_id, cdata in corr_arts.items():
                if isinstance(cdata, dict):
                    trajectories = cdata.get("pearson_trajectories", {})
                    cis = cdata.get("confidence_intervals", {})
                    if trajectories:
                        lines.append("  Pearson Trajectories by Metric Pair:")
                        for pair, vals in trajectories.items():
                            if isinstance(vals, list) and vals:
                                last = vals[-1]
                                lines.append(f"    {pair}: r = {last:.4f} (n_windows={len(vals)})")
                    if cis:
                        lines.append("  Fisher z Confidence Intervals:")
                        for pair, ci in cis.items():
                            if isinstance(ci, (list, tuple)) and len(ci) == 2:
                                lines.append(f"    {pair}: [{ci[0]:.4f}, {ci[1]:.4f}]")
        lines.append("")

        # D-03 Compression Artifacts (dip test statistics, excess mass z-scores)
        lines.append("D-03 Threshold Compression — Dip Test:")
        lines.append("")
        comp_arts = artifacts.get("compression_artifacts", {})
        if comp_arts:
            for det_id, cdata in comp_arts.items():
                if isinstance(cdata, dict):
                    dip_stats = cdata.get("dip_test_statistics", {})
                    em_z = cdata.get("excess_mass_z_scores", {})
                    if dip_stats:
                        lines.append("  Dip Statistics by Metric:")
                        for metric, val in dip_stats.items():
                            lines.append(f"    {metric}: D = {val:.4f}")
                    if em_z:
                        lines.append("  Excess Mass Z-Scores:")
                        for metric, val in em_z.items():
                            lines.append(f"    {metric}: z = {val:.4f}")
        lines.append("")

        # Detector execution metadata (power, MDE, CI widths if available)
        lines.append("Detector Execution Metadata:")
        lines.append("")
        for det_id in ["D-01", "D-02", "D-03"]:
            meta = det_meta.get(det_id, {})
            if isinstance(meta, dict) and meta:
                method = meta.get("method", "unknown")
                exec_time = meta.get("execution_time_seconds", 0)
                windows = meta.get("windows_analyzed", 0)
                observations = meta.get("observations_consumed", 0)
                ref = meta.get("scientific_reference", "")
                lines.append(f"  {det_id}:")
                lines.append(f"    Method: {method}")
                lines.append(f"    Execution Time: {exec_time:.3f}s")
                lines.append(f"    Windows: {windows}, Observations: {observations}")
                if ref:
                    lines.append(f"    Reference: {ref}")
        lines.append("")

        # Power analysis (if available from processing)
        lines.append("Power Analysis (if available):")
        lines.append("  Note: Power, MDE, and CI width data are computed in")
        lines.append("  processing/detection/power.py but not currently stored")
        lines.append("  in EvidencePackage. Future enhancement: store power")
        lines.append("  analysis results as additional statistical artifacts.")
        lines.append("")

        actions.append("View per-detector diagnostics")
        actions.append("View effect size interpretation guide")

        return ViewResult("Diagnostics", lines, actions, [])


class AssuranceView(ExplorationView):
    """Assurance view — assumption reports, threat assessments, limitations."""

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        state = workspace.state
        lines = []
        actions = []

        lines.append("=" * 72)
        lines.append("ASSURANCE (Previously Hidden)")
        lines.append("=" * 72)
        lines.append("")

        # Check if assurance report was generated
        # The assurance report is generated by build_assurance_report() but
        # currently not stored in WorkspaceState. It's called during analysis
        # but the output is discarded.
        lines.append("Assurance Report Status:")
        lines.append("  The assurance framework (src/miie/assurance/) generates:")
        lines.append("  - Assumption validation reports")
        lines.append("  - Evidence sufficiency reports")
        lines.append("  - Threats-to-validity assessments")
        lines.append("  - Limitation reports")
        lines.append("  - Audit trail records")
        lines.append("")
        lines.append("  These are generated during analysis but not currently")
        lines.append("  stored in WorkspaceState for post-analysis viewing.")
        lines.append("")
        lines.append("  Enhancement needed: Store assurance report in WorkspaceState")
        lines.append("  so it can be viewed in the workspace explorer.")
        lines.append("")

        # Show what assurance would cover based on available data
        ep = state.evidence_package
        if ep is not None:
            lines.append("Evidence Sufficiency (derived from available data):")
            obs_summary = getattr(ep, "observation_summary", None) or {}
            if isinstance(obs_summary, dict):
                total = obs_summary.get("total_observations", 0)
                quality = obs_summary.get("observation_quality", {})
                complete = quality.get("complete", 0) if isinstance(quality, dict) else 0
                partial = quality.get("partial", 0) if isinstance(quality, dict) else 0
                estimated = quality.get("estimated", 0) if isinstance(quality, dict) else 0

                lines.append(f"  Total observations: {total}")
                lines.append(f"  Complete: {complete}")
                lines.append(f"  Partial: {partial}")
                lines.append(f"  Estimated: {estimated}")

                if total > 0:
                    completeness = complete / total
                    if completeness >= 0.8:
                        lines.append(f"  Sufficiency: ADEQUATE ({completeness:.0%} complete)")
                    elif completeness >= 0.5:
                        lines.append(f"  Sufficiency: MARGINAL ({completeness:.0%} complete)")
                    else:
                        lines.append(f"  Sufficiency: INSUFFICIENT ({completeness:.0%} complete)")
            lines.append("")

            # Threats to validity (derived from detector assumptions)
            lines.append("Threats to Validity (derived from detector assumptions):")
            lines.append("  Internal validity:")
            lines.append("    - KS test assumes continuous data with independent observations")
            lines.append("    - Pearson assumes bivariate normality and linear relationships")
            lines.append("    - Dip test assumes unimodal null distribution")
            lines.append("")
            lines.append("  External validity:")
            lines.append("    - Results apply only to analyzed time windows")
            lines.append("    - Git-only metrics may not reflect full development process")
            lines.append("    - Small sample sizes reduce generalizability")
            lines.append("")
            lines.append("  Construct validity:")
            lines.append("    - Metrics are proxies for underlying constructs")
            lines.append("    - Entropy ratio assumes conventional commit format")
            lines.append("    - File change count does not account for file size or complexity")
        lines.append("")

        actions.append("View assumption details")
        actions.append("View limitation details")

        return ViewResult("Assurance", lines, actions, [])


class BenchmarkView(ExplorationView):
    """Benchmark exploration view."""

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        state = workspace.state
        lines = []
        actions = []

        lines.append("=" * 72)
        lines.append("BENCHMARK ANALYSIS")
        lines.append("=" * 72)
        lines.append("")

        # Check if benchmark was run
        bench = getattr(state, "benchmark", None)
        if bench is None:
            lines.append("Benchmark was not run for this analysis.")
            lines.append("")
            lines.append("To run benchmark, select 'Run Benchmark' from the menu.")
            return ViewResult("Benchmark", lines, actions, [])

        lines.append("Benchmark Status: Completed")
        lines.append("")

        # Show benchmark results if available
        if hasattr(bench, "comparison"):
            lines.append("Comparison Results:")
            lines.append(str(bench.comparison))

        lines.append("")
        actions.append("View benchmark comparison details")

        return ViewResult("Benchmark", lines, actions, [])


class RecommendationView(ExplorationView):
    """Recommendations exploration view."""

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        state = workspace.state
        lines = []
        actions = []

        lines.append("=" * 72)
        lines.append("RECOMMENDATIONS")
        lines.append("=" * 72)
        lines.append("")

        er = state.explanation_report
        if er is None:
            lines.append("No explanation report available.")
            return ViewResult("Recommendations", lines, actions, [])

        recommendations = getattr(er, "recommendations", []) or []
        lines.append(f"Total Recommendations: {len(recommendations)}")
        lines.append("")

        # Group by category
        categories: Dict[str, list] = {}
        for rec in recommendations:
            category = getattr(rec, "category", "general")
            if category not in categories:
                categories[category] = []
            categories[category].append(rec)

        for category, recs in sorted(categories.items()):
            lines.append(f"[{category.upper()}] ({len(recs)} items)")
            for rec in recs[:3]:
                reason = getattr(rec, "reason", "") or ""
                evidence = getattr(rec, "evidence", "") or ""
                confidence = getattr(rec, "confidence", 0.0) or 0.0
                lines.append(f"  Reason: {reason[:80]}...")
                lines.append(f"  Evidence: {evidence[:60]}...")
                lines.append(f"  Confidence: {confidence:.2f}")
                lines.append("")

        lines.append("")
        actions.append("Select a recommendation category")
        actions.append("View recommendation traceability")

        return ViewResult("Recommendations", lines, actions, [])


class SessionInfoView(ExplorationView):
    """Session information view."""

    def render(self, workspace: WorkspaceEngine) -> ViewResult:
        state = workspace.state
        lines = []
        actions = []

        lines.append("=" * 72)
        lines.append("SESSION INFORMATION")
        lines.append("=" * 72)
        lines.append("")

        lines.append(f"Workspace ID: {state.workspace_id}")
        lines.append(f"Created: {state.created_at}")
        lines.append(f"Repository: {state.repo_path}")
        lines.append(f"Total Commits: {state.total_commits}")
        lines.append(f"Contributors: {state.contributor_count}")
        lines.append(f"Windows Analyzed: {state.window_count}")
        lines.append("")

        lines.append("Configuration:")
        for key, value in state.config.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

        # Bookmarks
        bookmarks = workspace.get_bookmarks()
        lines.append(f"Bookmarks: {len(bookmarks)}")
        for bm in bookmarks:
            lines.append(f"  - {bm.get('name', 'Unnamed')} [{bm.get('section', '')}]")

        lines.append("")

        # Export history
        exports = workspace.get_export_history()
        lines.append(f"Exports: {len(exports)}")
        for ex in exports:
            lines.append(f"  - {ex.get('format', '')} at {ex.get('timestamp', '')}")

        lines.append("")
        actions.append("Add bookmark")
        actions.append("View export history")

        return ViewResult("Session", lines, actions, [])
