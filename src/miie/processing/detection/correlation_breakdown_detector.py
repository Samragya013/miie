"""
Correlation Breakdown Detector implementation for MIIE v1.0.
Implements D-02 detector per TFS Section 5.2.

Extended in v1.5 with detect_observations() that consumes ObservationWindow
data directly, using paired observations aligned by source_id instead of
positional truncation.

Reference: DES-v2.0 §16.4, §22, IMS-v1.0 Phase 5
"""

from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from miie.processing.detection.base import BaseDetector
from miie.processing.detection.diagnostics import d02_diagnostics
from miie.processing.detection.inference import StatisticalInferenceEngine
from miie.processing.detection.statistics import (
    fisher_z_ci,
    fisher_z_test,
    pearson_r,
    spearman_rho,
)
from miie.schemas.models import DetectorResult, MetricDataFrame


class CorrelationBreakdownDetector(BaseDetector):
    """
    D-02: Correlation Breakdown Detector

    Detects significant changes in correlation between metric pairs across windows.
    Implements Pearson correlation, Spearman rank correlation, and Fisher z-transformation
    for confidence interval-based breakdown detection.
    """

    def __init__(self):
        super().__init__(
            detector_id="D-02",
            detector_name="Correlation Breakdown Detector",
            supported_metrics=[f"M-{i:02d}" for i in range(1, 8)],  # M-01 through M-07
        )

        # Detection thresholds from TFS Section 5.2
        self.sudden_drop_threshold = 0.15  # PR-16D: calibrated from 0.30
        self.sign_reversal_min_correlation = 0.2
        self.gradual_erosion_slope_threshold = -0.1
        self.gradual_erosion_window_start_min = 0.3
        self.gradual_erosion_window_end_max = 0.1

    # ------------------------------------------------------------------
    # v1.5 Observation-Window Path
    # ------------------------------------------------------------------

    def detect_observations(
        self,
        windows: List[Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> DetectorResult:
        """Execute correlation breakdown detection on ObservationWindows.

        Aligns paired observations by source_id within each window,
        then computes correlation trajectories across windows.

        Args:
            windows: List of ObservationWindow objects.
            config: Optional overrides for detection thresholds.

        Returns:
            DetectorResult with breakdown analysis.
        """
        detector_outputs: Dict[str, Any] = {}

        # Apply config overrides
        sudden_drop = self.sudden_drop_threshold
        sign_min = self.sign_reversal_min_correlation
        erosion_slope = self.gradual_erosion_slope_threshold
        erosion_start = self.gradual_erosion_window_start_min
        erosion_end = self.gradual_erosion_window_end_max
        if config:
            sudden_drop = config.get("sudden_drop_threshold", sudden_drop)
            sign_min = config.get("sign_reversal_min_correlation", sign_min)
            erosion_slope = config.get("gradual_erosion_slope_threshold", erosion_slope)
            erosion_start = config.get("gradual_erosion_window_start_min", erosion_start)
            erosion_end = config.get("gradual_erosion_window_end_max", erosion_end)

        available_metrics = self._discover_metrics(windows)

        if len(available_metrics) < 2:
            detector_outputs[self.detector_id] = self._empty_output()
            return DetectorResult(detector_outputs=detector_outputs)

        metric_pairs = list(itertools.combinations(available_metrics, 2))
        window_ids = [w.window_id for w in windows]

        breakdown_events: List[Dict[str, Any]] = []
        breakdown_diagnostics: List[Dict[str, Any]] = []
        pearson_trajectories: Dict[str, List[Optional[float]]] = {}
        spearman_trajectories: Dict[str, List[Optional[float]]] = {}
        confidence_intervals: Dict[Tuple[str, str, str], List[float]] = {}

        for metric_i, metric_j in metric_pairs:
            pair_key = f"{metric_i}_{metric_j}"
            pearson_values: List[Optional[float]] = []
            spearman_values: List[Optional[float]] = []

            for window in windows:
                # Extract paired observations by source_id
                vals_i, vals_j = self._extract_paired_values(window, metric_i, metric_j)
                n = min(len(vals_i), len(vals_j))

                if n < 10:
                    pearson_values.append(None)
                    spearman_values.append(None)
                    continue

                # Use shared statistics
                r = pearson_r(vals_i, vals_j)
                rho = spearman_rho(vals_i, vals_j)

                pearson_values.append(float(r))
                spearman_values.append(float(rho))

                # Fisher z confidence interval
                ci_lower, ci_upper = fisher_z_ci(r, n)
                confidence_intervals[(metric_i, metric_j, window.window_id)] = [
                    ci_lower,
                    ci_upper,
                ]

            pearson_trajectories[pair_key] = pearson_values
            spearman_trajectories[pair_key] = spearman_values

            # Detect breakdowns
            pair_breakdowns = self._detect_breakdowns_for_pair(
                metric_i,
                metric_j,
                window_ids,
                pearson_values,
                spearman_values,
                confidence_intervals,
                sudden_drop,
                sign_min,
                erosion_slope,
                erosion_start,
                erosion_end,
            )
            breakdown_events.extend(pair_breakdowns)

            # PR-16B: Compute diagnostics for each breakdown event
            for bd in pair_breakdowns:
                wp = bd["window_pair"]
                # Find sample size and r for the first window in the pair
                r_for_diag = None
                n_for_diag = 0
                for idx, wid in enumerate(window_ids):
                    if wid == wp[0] and idx < len(pearson_values) and pearson_values[idx] is not None:
                        vi, vj = self._extract_paired_values(
                            windows[idx],
                            metric_i,
                            metric_j,
                        )
                        n_for_diag = min(len(vi), len(vj))
                        r_for_diag = pearson_values[idx]
                        break

                if r_for_diag is not None and n_for_diag >= 4:
                    diag = d02_diagnostics(
                        r=r_for_diag,
                        n=n_for_diag,
                        alpha=0.05,
                    )
                    diag["metric_pair"] = [metric_i, metric_j]
                    diag["breakdown_type"] = bd["breakdown_type"]
                    diag["window_pair"] = wp
                    breakdown_diagnostics.append(diag)

        breakdown_detected = len(breakdown_events) > 0
        breakdown_type = None
        if breakdown_detected:
            type_priority = {
                "sign_reversal": 0,
                "sudden_drop": 1,
                "gradual_erosion": 2,
                "confidence_exclusion": 3,
            }
            breakdown_type = min(
                [e["breakdown_type"] for e in breakdown_events if e["breakdown_type"]],
                key=lambda t: type_priority[t],
            )

        # ------------------------------------------------------------------
        # PR-16A: Multiple-testing correction (BH across metric pairs)
        # ------------------------------------------------------------------
        inference_families: List[Dict[str, Any]] = []
        for window_idx, wid in enumerate(window_ids):
            fam_p: List[float] = []
            fam_ids: List[str] = []
            for metric_i, metric_j in metric_pairs:
                pair_key = f"{metric_i}_{metric_j}"
                traj = pearson_trajectories.get(pair_key, [])
                if window_idx < len(traj) and traj[window_idx] is not None:
                    vals_i, vals_j = self._extract_paired_values(windows[window_idx], metric_i, metric_j)
                    n = min(len(vals_i), len(vals_j))
                    if n >= 4:
                        p_val = fisher_z_test(traj[window_idx], n)
                        fam_p.append(p_val)
                        fam_ids.append(f"{pair_key}_{wid}")

            if fam_p:
                result = StatisticalInferenceEngine.benjamini_hochberg(
                    fam_p,
                    alpha=0.05,
                    family_id=f"CORR_{wid}",
                )
                inference_families.append(StatisticalInferenceEngine.result_to_dict(result))

        total_corr_tests = sum(f["num_tests"] for f in inference_families)
        total_corr_rejections = sum(f["num_rejections"] for f in inference_families)

        detector_outputs[self.detector_id] = {
            "breakdown_detected": breakdown_detected,
            "breakdown_type": breakdown_type,
            "metric_pairs_analyzed": [f"{m1}_{m2}" for m1, m2 in metric_pairs],
            "breakdown_events": breakdown_events,
            "pearson_trajectories": pearson_trajectories,
            "spearman_trajectories": spearman_trajectories,
            "confidence_intervals": {f"{m1}_{m2}_{w}": ci for (m1, m2, w), ci in confidence_intervals.items()},
            "window_pairs_flagged": [[e["window_pair"][0], e["window_pair"][1]] for e in breakdown_events],
            "inference": {
                "method": "benjamini_hochberg",
                "alpha": 0.05,
                "families": inference_families,
                "summary": {
                    "total_correlation_tests": total_corr_tests,
                    "total_correlation_rejections": total_corr_rejections,
                },
            },
            "diagnostics": {
                "enabled": True,
                "per_event": breakdown_diagnostics,
            },
        }

        return DetectorResult(detector_outputs=detector_outputs)

    # ------------------------------------------------------------------
    # Legacy MetricDataFrame Path (unchanged for backward compatibility)
    # ------------------------------------------------------------------

    def validate_input(self, metric_dataframe: MetricDataFrame) -> bool:
        """
        Validate that at least two metrics are present for correlation analysis.

        Args:
            metric_dataframe: Input metrics to validate

        Returns:
            bool: True if at least two supported metrics are present
        """
        available_metrics = set(m for m in metric_dataframe.metrics.keys() if metric_dataframe.metrics[m] is not None)
        required_metrics = set(self.supported_metrics)
        return len(available_metrics.intersection(required_metrics)) >= 2

    def execute(self, metric_dataframe: MetricDataFrame) -> DetectorResult:
        """
        Execute correlation breakdown detection (legacy path).

        Args:
            metric_dataframe: Input metrics for detection

        Returns:
            DetectorResult: Detection outputs with breakdown analysis
        """
        detector_outputs: Dict[str, Any] = {}

        # Extract thresholds from self (matching main execute path)
        sudden_drop = self.sudden_drop_threshold
        sign_min = self.sign_reversal_min_correlation
        erosion_slope = self.gradual_erosion_slope_threshold
        erosion_start = self.gradual_erosion_window_start_min
        erosion_end = self.gradual_erosion_window_end_max

        available_metrics = [
            m
            for m in self.supported_metrics
            if m in metric_dataframe.metrics and metric_dataframe.metrics[m] is not None
        ]

        if len(available_metrics) < 2:
            detector_outputs[self.detector_id] = self._empty_output()
            return DetectorResult(detector_outputs=detector_outputs)

        metric_pairs = list(itertools.combinations(available_metrics, 2))

        window_sets = [set(metric_dataframe.metrics[m].keys()) for m in available_metrics]
        window_ids = sorted(set.union(*window_sets)) if window_sets else []

        breakdown_events: List[Dict[str, Any]] = []
        breakdown_diagnostics_legacy: List[Dict[str, Any]] = []
        pearson_trajectories: Dict[str, List[Optional[float]]] = {}
        spearman_trajectories: Dict[str, List[Optional[float]]] = {}
        confidence_intervals: Dict[Tuple[str, str, str], List[float]] = {}

        for metric_i, metric_j in metric_pairs:
            pair_key = f"{metric_i}_{metric_j}"
            pearson_values: List[Optional[float]] = []
            spearman_values: List[Optional[float]] = []

            for window_id in window_ids:
                vals_i = metric_dataframe.metrics[metric_i].get(window_id, [])
                vals_j = metric_dataframe.metrics[metric_j].get(window_id, [])

                n = min(len(vals_i), len(vals_j))
                if n < 10:
                    pearson_values.append(None)
                    spearman_values.append(None)
                    continue

                # Use shared statistics module
                r = pearson_r(vals_i, vals_j)
                rho = spearman_rho(vals_i, vals_j)

                pearson_values.append(float(r))
                spearman_values.append(float(rho))

                ci_lower, ci_upper = fisher_z_ci(r, n)
                confidence_intervals[(metric_i, metric_j, window_id)] = [
                    ci_lower,
                    ci_upper,
                ]

            pearson_trajectories[pair_key] = pearson_values
            spearman_trajectories[pair_key] = spearman_values

            pair_breakdowns = self._detect_breakdowns_for_pair(
                metric_i,
                metric_j,
                window_ids,
                pearson_values,
                spearman_values,
                confidence_intervals,
                sudden_drop,
                sign_min,
                erosion_slope,
                erosion_start,
                erosion_end,
            )
            breakdown_events.extend(pair_breakdowns)

            # PR-16B: Compute diagnostics for each breakdown event
            for bd in pair_breakdowns:
                wp = bd["window_pair"]
                r_for_diag = None
                n_for_diag = 0
                for idx, wid in enumerate(window_ids):
                    if wid == wp[0] and idx < len(pearson_values) and pearson_values[idx] is not None:
                        vi = metric_dataframe.metrics[metric_i].get(wid, [])
                        vj = metric_dataframe.metrics[metric_j].get(wid, [])
                        n_for_diag = min(len(vi), len(vj))
                        r_for_diag = pearson_values[idx]
                        break

                if r_for_diag is not None and n_for_diag >= 4:
                    diag = d02_diagnostics(
                        r=r_for_diag,
                        n=n_for_diag,
                        alpha=0.05,
                    )
                    diag["metric_pair"] = [metric_i, metric_j]
                    diag["breakdown_type"] = bd["breakdown_type"]
                    diag["window_pair"] = wp
                    breakdown_diagnostics_legacy.append(diag)

        breakdown_detected = len(breakdown_events) > 0
        breakdown_type = None
        if breakdown_detected:
            type_priority = {
                "sign_reversal": 0,
                "sudden_drop": 1,
                "gradual_erosion": 2,
                "confidence_exclusion": 3,
            }
            breakdown_type = min(
                [event["breakdown_type"] for event in breakdown_events if event["breakdown_type"]],
                key=lambda t: type_priority[t],
            )

        # ------------------------------------------------------------------
        # PR-16A: Multiple-testing correction (BH across metric pairs)
        # ------------------------------------------------------------------
        inference_families: List[Dict[str, Any]] = []
        for w_idx, wid in enumerate(window_ids):
            fam_p: List[float] = []
            fam_ids: List[str] = []
            for metric_i, metric_j in metric_pairs:
                vals_i = metric_dataframe.metrics[metric_i].get(wid, [])
                vals_j = metric_dataframe.metrics[metric_j].get(wid, [])
                n = min(len(vals_i), len(vals_j))
                if n >= 4:
                    r = pearson_r(vals_i, vals_j)
                    p_val = fisher_z_test(r, n)
                    fam_p.append(p_val)
                    fam_ids.append(f"{metric_i}_{metric_j}_{wid}")

            if fam_p:
                result = StatisticalInferenceEngine.benjamini_hochberg(
                    fam_p,
                    alpha=0.05,
                    family_id=f"CORR_{wid}",
                )
                inference_families.append(StatisticalInferenceEngine.result_to_dict(result))

        total_corr_tests = sum(f["num_tests"] for f in inference_families)
        total_corr_rejections = sum(f["num_rejections"] for f in inference_families)

        detector_outputs[self.detector_id] = {
            "breakdown_detected": breakdown_detected,
            "breakdown_type": breakdown_type,
            "metric_pairs_analyzed": [f"{m1}_{m2}" for m1, m2 in metric_pairs],
            "breakdown_events": breakdown_events,
            "pearson_trajectories": pearson_trajectories,
            "spearman_trajectories": spearman_trajectories,
            "confidence_intervals": {f"{m1}_{m2}_{w}": ci for (m1, m2, w), ci in confidence_intervals.items()},
            "window_pairs_flagged": [[event["window_pair"][0], event["window_pair"][1]] for event in breakdown_events],
            "inference": {
                "method": "benjamini_hochberg",
                "alpha": 0.05,
                "families": inference_families,
                "summary": {
                    "total_correlation_tests": total_corr_tests,
                    "total_correlation_rejections": total_corr_rejections,
                },
            },
            "diagnostics": {
                "enabled": True,
                "per_event": breakdown_diagnostics_legacy,
            },
        }

        return DetectorResult(detector_outputs=detector_outputs)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _discover_metrics(self, windows: List[Any]) -> List[str]:
        """Find all supported metric IDs present in any window."""
        found: set[str] = set()
        for w in windows:
            for obs in w.observations:
                if obs.metric_id in self.supported_metrics:
                    found.add(obs.metric_id)
        return sorted(found)

    def _extract_paired_values(self, window: Any, metric_i: str, metric_j: str) -> Tuple[List[float], List[float]]:
        """Extract aligned observation values for two metrics by source_id."""
        obs_i: Dict[str, float] = {}
        obs_j: Dict[str, float] = {}
        for obs in window.observations:
            if obs.metric_id == metric_i and obs.source_id not in obs_i:
                obs_i[obs.source_id] = obs.value
            elif obs.metric_id == metric_j and obs.source_id not in obs_j:
                obs_j[obs.source_id] = obs.value

        common = sorted(set(obs_i.keys()) & set(obs_j.keys()))
        if not common:
            return [], []

        return [obs_i[s] for s in common], [obs_j[s] for s in common]

    def _detect_breakdowns_for_pair(
        self,
        metric_i: str,
        metric_j: str,
        window_ids: List[str],
        pearson_values: List[Optional[float]],
        spearman_values: List[Optional[float]],
        confidence_intervals: Dict[Tuple[str, str, str], List[float]],
        sudden_drop_threshold: float = 0.3,
        sign_reversal_min: float = 0.2,
        erosion_slope_threshold: float = -0.1,
        erosion_start_min: float = 0.3,
        erosion_end_max: float = 0.1,
    ) -> List[Dict[str, Any]]:
        """Detect breakdowns for a single metric pair across windows.

        Uses max(|Pearson|, |Spearman|) for breakdown detection (FIX-4).
        """
        breakdown_events: List[Dict[str, Any]] = []
        K = len(window_ids)

        if K < 2:
            return breakdown_events

        effective: List[Optional[float]] = []
        for k in range(K):
            p = pearson_values[k] if k < len(pearson_values) else None
            s = spearman_values[k] if k < len(spearman_values) else None
            if p is not None and s is not None:
                effective.append(max(abs(p), abs(s)) * (1 if (p if abs(p) >= abs(s) else s) >= 0 else -1))
            elif p is not None:
                effective.append(p)
            elif s is not None:
                effective.append(s)
            else:
                effective.append(None)

        # Breakdown Type 1: Sudden drop
        for k in range(K - 1):
            if effective[k] is None or effective[k + 1] is None:
                continue
            delta = abs(effective[k + 1] - effective[k])
            if delta > sudden_drop_threshold:
                breakdown_events.append(
                    {
                        "metric_pair": [metric_i, metric_j],
                        "breakdown_type": "sudden_drop",
                        "window_pair": [window_ids[k], window_ids[k + 1]],
                        "delta_effective": delta,
                        "pearson_values": [pearson_values[k], pearson_values[k + 1]],
                        "spearman_values": [
                            spearman_values[k] if k < len(spearman_values) else None,
                            spearman_values[k + 1] if k + 1 < len(spearman_values) else None,
                        ],
                        "detection_method": "sudden_drop",
                    }
                )

        # Breakdown Type 2: Sign reversal
        for k in range(K - 1):
            if effective[k] is None or effective[k + 1] is None:
                continue
            if (
                np.sign(effective[k]) != np.sign(effective[k + 1])
                and abs(effective[k]) > sign_reversal_min
                and abs(effective[k + 1]) > sign_reversal_min
            ):
                breakdown_events.append(
                    {
                        "metric_pair": [metric_i, metric_j],
                        "breakdown_type": "sign_reversal",
                        "window_pair": [window_ids[k], window_ids[k + 1]],
                        "effective_values": [effective[k], effective[k + 1]],
                        "pearson_values": [pearson_values[k], pearson_values[k + 1]],
                        "spearman_values": [
                            spearman_values[k] if k < len(spearman_values) else None,
                            spearman_values[k + 1] if k + 1 < len(spearman_values) else None,
                        ],
                        "detection_method": "sign_reversal",
                    }
                )

        # Breakdown Type 3: Gradual erosion (requires K >= 4)
        if K >= 4:
            if (
                effective[0] is not None
                and effective[-1] is not None
                and effective[0] > erosion_start_min
                and effective[-1] < erosion_end_max
            ):
                valid_indices = []
                valid_values = []
                for idx, val in enumerate(effective):
                    if val is not None:
                        valid_indices.append(idx)
                        valid_values.append(val)

                if len(valid_indices) >= 2:
                    x = np.array(valid_indices, dtype=float)
                    y = np.array(valid_values, dtype=float)
                    x_mean = np.mean(x)
                    y_mean = np.mean(y)
                    numerator = np.sum((x - x_mean) * (y - y_mean))
                    denominator = np.sum((x - x_mean) ** 2)
                    if denominator != 0:
                        slope = numerator / denominator
                        if slope < erosion_slope_threshold:
                            breakdown_events.append(
                                {
                                    "metric_pair": [metric_i, metric_j],
                                    "breakdown_type": "gradual_erosion",
                                    "window_pair": [window_ids[0], window_ids[-1]],
                                    "slope": slope,
                                    "effective_values": effective,
                                    "pearson_values": pearson_values,
                                    "spearman_values": spearman_values,
                                    "detection_method": "gradual_erosion",
                                }
                            )

        # Breakdown Type 4: Confidence interval exclusion
        for k in range(K - 1):
            ci_key_curr = (metric_i, metric_j, window_ids[k])
            ci_key_next = (metric_i, metric_j, window_ids[k + 1])
            if ci_key_curr in confidence_intervals and ci_key_next in confidence_intervals:
                ci_curr = confidence_intervals[ci_key_curr]
                ci_next = confidence_intervals[ci_key_next]
                if ci_curr[1] < ci_next[0] or ci_next[1] < ci_curr[0]:
                    breakdown_events.append(
                        {
                            "metric_pair": [metric_i, metric_j],
                            "breakdown_type": "confidence_exclusion",
                            "window_pair": [window_ids[k], window_ids[k + 1]],
                            "confidence_intervals": [ci_curr, ci_next],
                            "effective_values": [effective[k], effective[k + 1]],
                            "pearson_values": [pearson_values[k], pearson_values[k + 1]],
                            "spearman_values": [
                                spearman_values[k] if k < len(spearman_values) else None,
                                spearman_values[k + 1] if k + 1 < len(spearman_values) else None,
                            ],
                            "detection_method": "confidence_exclusion",
                        }
                    )

        return breakdown_events

    def _empty_output(self) -> Dict[str, Any]:
        """Return the empty (no-breakdown) output structure."""
        return {
            "breakdown_detected": False,
            "breakdown_type": None,
            "metric_pairs_analyzed": [],
            "breakdown_events": [],
            "pearson_trajectories": {},
            "spearman_trajectories": {},
            "confidence_intervals": {},
            "window_pairs_flagged": [],
        }
