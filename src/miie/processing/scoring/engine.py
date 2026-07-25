"""Scoring Engine Implementation.
Implements the IScoringEngine interface for computing integrity and confidence scores.

Extended: IMS Phase 7 (Scoring Refactor) for observation-level scoring.
Extended: IMS Phase 3 (Integrity Score Observation Enhancement).
Extended: IMS Phase 4 (Confidence Score Observation Factors).
Extended: IMS Phase 7 (Deterministic Scoring).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from miie.contracts.errors import ValidationError
from miie.contracts.interfaces import IScoringEngine
from miie.schemas.models import (
    ConfidenceScore,
    DetectorResults,
    EvidencePackage,
    IntegrityScore,
    MetricDataFrame,
    ScorePackage,
    WindowDefinition,
)

from .utils import (
    compute_balance_factor,
    compute_clamped,
    compute_coverage_ratio,
    compute_cv,
    compute_detector_success_factor,
    compute_mean,
    compute_missing_data_factor,
    compute_observation_quality_factor,
    compute_sample_size_factor,
    compute_variance_factor,
    safe_divide,
)


class ScoringEngine(IScoringEngine):
    """Scoring Engine implementation that computes integrity and confidence scores.

    Extended: IMS Phase 7 (Scoring Refactor) for observation-level scoring.

    The scoring engine now accepts an optional EvidencePackage parameter to leverage
    observation-level metadata for more accurate scoring while preserving backward
    compatibility with the legacy DetectorResults-only interface.
    """

    # TFS Section 6.3 default detector weights
    DEFAULT_W1 = 0.40  # D-01 (Distributional Drift)
    DEFAULT_W2 = 0.35  # D-02 (Correlation Breakdown)
    DEFAULT_W3 = 0.25  # D-03 (Threshold Compression)

    # TFS Section 7.4-7.5 default thresholds
    SAMPLE_SIZE_TARGET = 50.0
    VARIANCE_CV_THRESHOLD = 0.5

    def __init__(self):
        """Initialize the scoring engine."""

    def compute_integrity_score(
        self,
        detector_results: DetectorResults,
        metric_dataframe: MetricDataFrame,
        windows: List[WindowDefinition],
        detector_weights: Optional[Dict[str, float]] = None,
        evidence_package: Optional[EvidencePackage] = None,
    ) -> ScorePackage:
        """Compute integrity and confidence scores.

        Implements TFS Section 6 (Integrity Score) and TFS Section 7 (Confidence Score).

        When evidence_package is provided, the scoring engine uses observation-level
        metadata for more accurate scoring while preserving the mathematical equations.

        Args:
            detector_results: Container for detector outputs
            metric_dataframe: Container for extracted metrics
            windows: List of window definitions used in analysis
            detector_weights: Optional weights for detectors (defaults to equal weights)
            evidence_package: Optional evidence package with observation-level metadata

        Returns:
            ScorePackage: Container for computed integrity and confidence scores
        """
        # Handle edge case: no detectors or no windows or no metrics
        # Return neutral scores instead of raising validation error for edge cases
        if not detector_results.detector_outputs or not windows or not metric_dataframe.metrics:
            return ScorePackage(
                integrity=IntegrityScore(overall=1.0, per_metric={}, formula_version="TFS_v1.0"),
                confidence=ConfidenceScore(overall=0.0, factors={}, band="low", level="score"),
                timestamp=datetime.now(timezone.utc),
                config_hash="",
                formula_version="TFS_v1.0",
            )

        # Set up detector weights (equal weights if not provided)
        detector_ids = sorted(detector_results.detector_outputs.keys())
        if detector_weights is None:
            detector_weights = {det_id: 1.0 / len(detector_ids) for det_id in detector_ids}
        else:
            weight_sum = sum(detector_weights.values())
            if weight_sum <= 0:
                raise ValidationError("Sum of detector weights must be positive")
            detector_weights = {det_id: weight / weight_sum for det_id, weight in detector_weights.items()}

        # Extract observation metadata once for both IS and CS
        observation_metadata = self._extract_observation_metadata(evidence_package)

        # Compute integrity score using TFS Section 6 formula
        # Enhanced with observation-level severity weighting (IMS Phase 3)
        integrity_result = self._compute_integrity_score_tfs6(
            detector_results,
            metric_dataframe,
            windows,
            detector_weights,
            observation_metadata,
        )

        # Compute confidence score using TFS Section 7 formula
        # Enhanced with observation-level evidence when available (IMS Phase 4)
        confidence_result = self._compute_confidence_score_tfs7(
            detector_results,
            metric_dataframe,
            windows,
            evidence_package,
            observation_metadata,
        )

        return ScorePackage(
            integrity=integrity_result,
            confidence=confidence_result,
            timestamp=datetime.now(timezone.utc),
            config_hash="",
            formula_version="TFS_v1.0",
        )

    def _compute_integrity_score_tfs6(
        self,
        detector_results: DetectorResults,
        metric_dataframe: MetricDataFrame,
        windows: List[WindowDefinition],
        detector_weights: Dict[str, float],
        observation_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compute integrity score per TFS Section 6.3.

        IS = 1.0 - (w₁ × d₁ + w₂ × d₂ + w₃ × d₃)

        When observation_metadata is provided:
        - Metrics with low observation coverage have their severity reduced
          (insufficient evidence = lower severity contribution)
        - Per-metric observation counts inform the weighting of each detector's
          severity contribution

        Args:
            detector_results: Container for detector outputs
            metric_dataframe: Container for extracted metrics
            windows: List of window definitions
            detector_weights: Dict mapping detector_id -> weight
            observation_metadata: Optional observation metadata from evidence package

        Returns:
            Dict with "overall" and "per_metric" keys
        """
        if not detector_results.detector_outputs:
            return {"overall": 1.0, "per_metric": {}}

        # Get all available metrics (sorted for deterministic ordering)
        available_metrics = sorted(metric_dataframe.metrics.keys()) if metric_dataframe.metrics else []

        if not available_metrics:
            return {"overall": 1.0, "per_metric": {}}

        per_metric_scores: Dict[str, float] = {}

        for metric_id in available_metrics:
            # Get severity scores for each detector for this metric
            d1 = self._get_drift_severity(detector_results, metric_id, windows)
            d2 = self._get_breakdown_severity(detector_results, metric_id, windows)
            d3 = self._get_compression_severity(detector_results, metric_id, windows)

            # Apply observation-aware severity adjustment (IMS Phase 3)
            # When observation coverage is low, reduce severity proportionally
            # This prevents over-penalizing when there is insufficient evidence
            severity_multiplier = self._compute_observation_severity_multiplier(metric_id, observation_metadata)

            # TFS Section 6.3: IS_metric = 1.0 - (w₁ × d₁ + w₂ × d₂ + w₃ × d₃)
            w1 = detector_weights.get("D-01", self.DEFAULT_W1)
            w2 = detector_weights.get("D-02", self.DEFAULT_W2)
            w3 = detector_weights.get("D-03", self.DEFAULT_W3)

            is_metric = 1.0 - (w1 * d1 + w2 * d2 + w3 * d3)

            # Apply observation-based severity adjustment
            # severity_multiplier in [0, 1]: 1.0 = full severity, <1.0 = reduced severity
            is_metric = is_metric * severity_multiplier + (1.0 - severity_multiplier)
            is_metric = compute_clamped(is_metric)

            per_metric_scores[metric_id] = is_metric

        # Calculate overall integrity score as mean of per-metric scores (TFS Section 6.4)
        overall_score = compute_clamped(compute_mean(list(per_metric_scores.values())))

        return IntegrityScore(
            overall=overall_score,
            per_metric=per_metric_scores,
            formula_version="TFS_v1.0",
        )

    def _compute_observation_severity_multiplier(
        self,
        metric_id: str,
        observation_metadata: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Compute a severity multiplier based on observation coverage.

        When observation coverage is low for a metric, the severity of any
        detected issues should be reduced (insufficient evidence = lower confidence
        in the severity assessment).

        The multiplier is in [0.5, 1.0]:
        - 1.0: Full observation coverage, full severity
        - 0.5: No observations, half severity (minimum floor)

        Args:
            metric_id: The metric to check
            observation_metadata: Optional observation metadata from evidence package

        Returns:
            Severity multiplier in [0.5, 1.0]
        """
        if not observation_metadata:
            return 1.0

        per_metric_obs = observation_metadata.get("per_metric_observations", {})
        if not per_metric_obs:
            return 1.0

        obs_data = per_metric_obs.get(metric_id)
        if not isinstance(obs_data, dict):
            return 1.0

        obs_count = obs_data.get("count", 0)
        _window_count = obs_data.get("window_count", 0)

        if obs_count <= 0:
            return 0.5  # No observations: reduce severity by half

        # Coverage ratio: observations relative to a target
        # More observations = higher multiplier (closer to 1.0)
        coverage = compute_coverage_ratio(obs_count, self.SAMPLE_SIZE_TARGET)
        # Map coverage [0, 1] to multiplier [0.5, 1.0]
        return 0.5 + 0.5 * coverage

    def _get_drift_severity(
        self,
        detector_results: DetectorResults,
        metric_id: str,
        windows: List[WindowDefinition],
    ) -> float:
        """Get D-01 drift severity for a metric per TFS Section 6.3.

        d₁ = min(1.0, mean(drift_magnitude across all window pairs))
        where drift_magnitude = ks_statistic (normalized to [0,1] by capping at 0.5)
        """
        drift_magnitudes: List[float] = []

        for det_id, det_output in detector_results.detector_outputs.items():
            if det_id == "D-01":
                # Detector failed — assign moderate uncertainty penalty
                if isinstance(det_output, dict) and det_output.get("status") in ("error", "skipped"):
                    return 0.3  # Moderate penalty for unknown detector state

                drift_detected = False
                drift_magnitude = 0.0

                # Check for boolean flag
                if "drift_detected" in det_output and det_output["drift_detected"] is True:
                    drift_detected = True
                    if "ks_statistic" in det_output:
                        try:
                            ks_stat = float(det_output["ks_statistic"])
                            drift_magnitude = min(1.0, ks_stat / 0.5)
                        except (ValueError, TypeError):
                            drift_magnitude = 1.0
                    else:
                        drift_magnitude = 1.0

                # Check for numeric score/severity fields
                if not drift_detected:
                    for score_field in ["score", "severity", "drift_score"]:
                        if score_field in det_output:
                            try:
                                val = float(det_output[score_field])
                                drift_magnitude = compute_clamped(val)
                                drift_detected = True
                                break
                            except (ValueError, TypeError):
                                pass

                # Fallback: extract severity from structured drift_events
                if not drift_detected and isinstance(det_output.get("drift_events"), list):
                    events = det_output["drift_events"]
                    if events:
                        severities = []
                        for e in events:
                            if not isinstance(e, dict):
                                continue
                            for field in ("severity", "ks_statistic", "psi_value"):
                                if field in e:
                                    try:
                                        severities.append(float(e[field]))
                                    except (ValueError, TypeError):
                                        pass
                                    break
                        if severities:
                            drift_magnitude = compute_clamped(max(severities))
                            drift_detected = True

                if drift_detected:
                    drift_magnitudes.append(drift_magnitude)

        return compute_clamped(compute_mean(drift_magnitudes)) if drift_magnitudes else 0.0

    def _get_breakdown_severity(
        self,
        detector_results: DetectorResults,
        metric_id: str,
        windows: List[WindowDefinition],
    ) -> float:
        """Get D-02 breakdown severity for a metric per TFS Section 6.3.

        d₂ = min(1.0, mean(breakdown_magnitude across all metric pairs and window pairs))
        where breakdown_magnitude = |delta_r| / 0.3 (capped at 1.0)
        """
        breakdown_magnitudes: List[float] = []

        for det_id, det_output in detector_results.detector_outputs.items():
            if det_id == "D-02":
                if isinstance(det_output, dict) and det_output.get("status") in ("error", "skipped"):
                    return 0.3
                breakdown_detected = False
                breakdown_magnitude = 0.0

                if "correlation_breakdown" in det_output and det_output["correlation_breakdown"] is True:
                    breakdown_detected = True
                    if "delta_r" in det_output:
                        try:
                            delta_r = float(det_output["delta_r"])
                            breakdown_magnitude = min(1.0, abs(delta_r) / 0.3)
                        except (ValueError, TypeError):
                            breakdown_magnitude = 1.0
                    else:
                        breakdown_magnitude = 1.0

                if not breakdown_detected:
                    for score_field in ["score", "severity", "breakdown_score"]:
                        if score_field in det_output:
                            try:
                                val = float(det_output[score_field])
                                breakdown_magnitude = compute_clamped(val)
                                breakdown_detected = True
                                break
                            except (ValueError, TypeError):
                                pass

                # Fallback: extract severity from structured breakdown_events
                if not breakdown_detected and isinstance(det_output.get("breakdown_events"), list):
                    events = det_output["breakdown_events"]
                    if events:
                        severities = []
                        for e in events:
                            if not isinstance(e, dict):
                                continue
                            for field in ("severity", "delta_pearson", "slope"):
                                if field in e:
                                    try:
                                        val = abs(float(e[field]))
                                        severities.append(min(1.0, val / 0.3))
                                    except (ValueError, TypeError):
                                        pass
                                    break
                        if severities:
                            breakdown_magnitude = compute_clamped(max(severities))
                            breakdown_detected = True

                if breakdown_detected:
                    breakdown_magnitudes.append(breakdown_magnitude)

        return compute_clamped(compute_mean(breakdown_magnitudes)) if breakdown_magnitudes else 0.0

    def _get_compression_severity(
        self,
        detector_results: DetectorResults,
        metric_id: str,
        windows: List[WindowDefinition],
    ) -> float:
        """Get D-03 compression severity for a metric per TFS Section 6.3.

        d₃ = min(1.0, mean(compression_index across all thresholds and windows))
        where compression_index is already in [0,1]
        """
        compression_indices: List[float] = []

        for det_id, det_output in detector_results.detector_outputs.items():
            if det_id == "D-03":
                if isinstance(det_output, dict) and det_output.get("status") in ("error", "skipped"):
                    return 0.3
                compression_detected = False
                compression_index = 0.0

                if "threshold_compressed" in det_output and det_output["threshold_compressed"] is True:
                    compression_detected = True
                    if "compression_index" in det_output:
                        try:
                            compression_index = float(det_output["compression_index"])
                            compression_index = compute_clamped(compression_index)
                        except (ValueError, TypeError):
                            compression_index = 1.0
                    else:
                        compression_index = 1.0

                if not compression_detected:
                    for score_field in ["score", "severity", "compression_score"]:
                        if score_field in det_output:
                            try:
                                val = float(det_output[score_field])
                                compression_index = compute_clamped(val)
                                compression_detected = True
                                break
                            except (ValueError, TypeError):
                                pass

                # Fallback: extract severity from structured compression_events
                if not compression_detected and isinstance(det_output.get("compression_events"), list):
                    events = det_output["compression_events"]
                    if events:
                        severities = []
                        for e in events:
                            if not isinstance(e, dict):
                                continue
                            for field in ("severity", "compression_index", "excess_mass_z"):
                                if field in e:
                                    try:
                                        severities.append(float(e[field]))
                                    except (ValueError, TypeError):
                                        pass
                                    break
                        if severities:
                            compression_index = compute_clamped(max(severities))
                            compression_detected = True

                if compression_detected:
                    compression_indices.append(compression_index)

        return compute_clamped(compute_mean(compression_indices)) if compression_indices else 0.0

    def _compute_confidence_score_tfs7(
        self,
        detector_results: DetectorResults,
        metric_dataframe: MetricDataFrame,
        windows: List[WindowDefinition],
        evidence_package: Optional[EvidencePackage] = None,
        observation_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compute score confidence (C_s) per TFS Section 7.4-7.5.

        Formula: C_s = β₁ × β₂ × β₃ × β₄ × β₅ × β₆

        Factors (β):
            β₁ (sample_size_adequacy): min(1, mean_n/50) — Is the overall sample adequate?
            β₂ (variance_stability): 1 - min(1, mean_CV/0.5) — Are metrics stable across windows?
            β₃ (data_completeness): 1 - (missing/total) — Is data complete?
            β₄ (window_balance): 1 - min(1, std/mean) — Are windows balanced?
            β₅ (detector_coverage): successful/total — Did detectors execute successfully?
            β₆ (evidence_quality): (complete + 0.5·partial)/total — Is observation evidence high quality?

        Composition rationale: Multiplicative because all factors are necessary conditions.
        If any factor is zero (e.g., no detectors executed, no observations available),
        the entire score confidence must be zero. The multiplicative model enforces this.

        Reference: 01_CONFIDENCE_MODEL_UNIFICATION.md §7.4

        Args:
            detector_results: Container for detector outputs
            metric_dataframe: Container for extracted metrics
            windows: List of window definitions
            evidence_package: Optional evidence package
            observation_metadata: Optional pre-extracted observation metadata

        Returns:
            Dict with "overall" and "factors" keys
        """
        if not windows or not metric_dataframe.metrics:
            return {"overall": 0.0, "factors": {}}

        if observation_metadata is None:
            observation_metadata = self._extract_observation_metadata(evidence_package)

        # β₁: Sample Size Factor - enhanced with observation counts
        beta_1 = self._compute_sample_size_factor(metric_dataframe, windows, observation_metadata)

        # β₂: Variance Factor
        beta_2 = self._compute_variance_factor(metric_dataframe, windows)

        # β₃: Missing Data Factor - enhanced with observation coverage
        beta_3 = self._compute_missing_data_factor(metric_dataframe, windows, observation_metadata)

        # β₄: Window Balance Factor - enhanced with observation counts
        beta_4 = self._compute_window_balance_factor(windows, observation_metadata, metric_dataframe)

        # β₅: Detector Success Factor - enhanced with execution metadata
        beta_5 = self._compute_detector_success_factor(detector_results, metric_dataframe, evidence_package)

        # β₆: Observation Quality Factor (IMS Phase 4 extension)
        beta_6 = self._compute_observation_quality_factor(observation_metadata)

        # C_s = β₁ × β₂ × β₃ × β₄ × β₅ × β₆
        confidence_score = beta_1 * beta_2 * beta_3 * beta_4 * beta_5 * beta_6
        confidence_score = compute_clamped(confidence_score)

        # Deterministic factor ordering (IMS Phase 7)
        factors = {
            "sample_size": beta_1,
            "variance": beta_2,
            "missing_data": beta_3,
            "window_balance": beta_4,
            "detector_success": beta_5,
            "observation_quality": beta_6,
        }

        # Determine confidence band
        if confidence_score >= 0.8:
            band = "high"
        elif confidence_score >= 0.5:
            band = "medium"
        else:
            band = "low"

        return ConfidenceScore(
            overall=confidence_score,
            factors=factors,
            band=band,
            level="score",
        )

    def _extract_observation_metadata(self, evidence_package: Optional[EvidencePackage]) -> Dict[str, Any]:
        """Extract observation metadata from evidence package.

        Args:
            evidence_package: Optional evidence package with observation-level metadata

        Returns:
            Dictionary containing extracted observation metadata
        """
        metadata: Dict[str, Any] = {
            "total_observations": 0,
            "per_metric_observations": {},
            "per_window_observations": {},
            "observation_quality": {},
            "detector_execution_metadata": {},
        }

        if evidence_package is None:
            return metadata

        if hasattr(evidence_package, "observation_summary") and evidence_package.observation_summary:
            obs_summary = evidence_package.observation_summary
            metadata["total_observations"] = obs_summary.get("total_observations", 0)
            metadata["per_metric_observations"] = obs_summary.get("per_metric", {})
            metadata["observation_quality"] = obs_summary.get("observation_quality", {})

        if hasattr(evidence_package, "detector_execution_metadata") and evidence_package.detector_execution_metadata:
            metadata["detector_execution_metadata"] = evidence_package.detector_execution_metadata

        return metadata

    def _compute_sample_size_factor(
        self,
        metric_dataframe: MetricDataFrame,
        windows: List[WindowDefinition],
        observation_metadata: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Compute f₁: min(1.0, mean_n / 50.0)

        Enhanced with observation counts when available.

        Args:
            metric_dataframe: Container for extracted metrics
            windows: List of window definitions
            observation_metadata: Optional observation metadata from evidence package

        Returns:
            Sample size factor in [0, 1]
        """
        # Try to use observation counts first
        if observation_metadata and observation_metadata.get("per_metric_observations"):
            per_metric_obs = observation_metadata["per_metric_observations"]
            if per_metric_obs:
                counts = []
                for metric_id, obs_data in per_metric_obs.items():
                    if isinstance(obs_data, dict) and "count" in obs_data:
                        counts.append(float(obs_data["count"]))

                if counts:
                    mean_n = compute_mean(counts)
                    return compute_sample_size_factor(mean_n, self.SAMPLE_SIZE_TARGET)

        # Fallback to metric_dataframe-based calculation
        if not metric_dataframe.metrics or not windows:
            return 0.0

        total_points = 0
        metric_count = 0

        for metric_id, metric_series in metric_dataframe.metrics.items():
            if metric_series is None or not isinstance(metric_series, dict):
                continue
            point_count = 0
            for value_list in metric_series.values():
                if isinstance(value_list, list):
                    point_count += sum(1 for v in value_list if v is not None)

            if point_count > 0:
                total_points += point_count
                metric_count += 1

        mean_n = safe_divide(float(total_points), float(metric_count))
        return compute_sample_size_factor(mean_n, self.SAMPLE_SIZE_TARGET)

    def _compute_variance_factor(
        self,
        metric_dataframe: MetricDataFrame,
        windows: List[WindowDefinition],
    ) -> float:
        """Compute f₂: 1.0 - min(1.0, mean_CV / 0.5)

        mean_CV = mean(CV for all valid windows)
        CV = std(W[M]) / |mean(W[M])| (with special handling for mean=0)
        """
        if not metric_dataframe.metrics or not windows:
            return 0.5  # Default moderate confidence when no data

        cv_values: List[float] = []

        for metric_id, metric_series in metric_dataframe.metrics.items():
            if metric_series is None or not isinstance(metric_series, dict):
                continue
            for window_key, value_list in metric_series.items():
                if isinstance(value_list, list) and len(value_list) > 0:
                    valid_values = [v for v in value_list if v is not None]
                    if len(valid_values) >= 2:
                        cv = compute_cv(valid_values)
                        cv_values.append(cv)

        mean_cv = compute_mean(cv_values) if cv_values else 0.0
        return compute_variance_factor(mean_cv, self.VARIANCE_CV_THRESHOLD)

    def _compute_missing_data_factor(
        self,
        metric_dataframe: MetricDataFrame,
        windows: List[WindowDefinition],
        observation_metadata: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Compute f₃: 1.0 - (missing_pairs / total_pairs)

        Enhanced with observation coverage when available.

        Args:
            metric_dataframe: Container for extracted metrics
            windows: List of window definitions
            observation_metadata: Optional observation metadata from evidence package

        Returns:
            Missing data factor in [0, 1]
        """
        if not metric_dataframe.metrics or not windows:
            return 0.0

        # Try to use observation coverage first
        if observation_metadata and observation_metadata.get("per_metric_observations"):
            per_metric_obs = observation_metadata["per_metric_observations"]
            if per_metric_obs:
                num_metrics = len(metric_dataframe.metrics)
                num_windows = len(windows)
                total_pairs = num_metrics * num_windows

                if total_pairs == 0:
                    return 0.0

                missing_pairs = 0
                for metric_id in metric_dataframe.metrics.keys():
                    if metric_id not in per_metric_obs:
                        missing_pairs += num_windows
                    else:
                        obs_data = per_metric_obs[metric_id]
                        if isinstance(obs_data, dict):
                            obs_count = obs_data.get("count", 0)
                            if obs_count == 0:
                                missing_pairs += num_windows

                return compute_missing_data_factor(missing_pairs, total_pairs)

        # Fallback to metric_dataframe-based calculation
        num_metrics = len(metric_dataframe.metrics)
        num_windows = len(windows)
        total_pairs = num_metrics * num_windows

        if total_pairs == 0:
            return 0.0

        # Aggregate metrics only need 1 observation total, not per-window
        _AGGREGATE_METRICS = {"M-01", "M-04", "M-07"}

        missing_pairs = 0

        for metric_id, metric_series in metric_dataframe.metrics.items():
            if not metric_series or all(
                not isinstance(v, list) or len(v) == 0 or all(x is None for x in v) for v in metric_series.values()
            ):
                missing_pairs += num_windows
            else:
                # For aggregate metrics, count as present if any window has data
                if metric_id in _AGGREGATE_METRICS:
                    has_any = False
                    for window_key in metric_series.keys():
                        value_list = metric_series[window_key]
                        if (
                            isinstance(value_list, list)
                            and len(value_list) > 0
                            and any(x is not None for x in value_list)
                        ):
                            has_any = True
                            break
                    if not has_any:
                        missing_pairs += num_windows
                    # else: aggregate metric has data, don't count missing
                else:
                    for window_key in metric_series.keys():
                        value_list = metric_series[window_key]
                        if (
                            not isinstance(value_list, list)
                            or len(value_list) == 0
                            or all(x is None for x in value_list)
                        ):
                            missing_pairs += 1

        return compute_missing_data_factor(missing_pairs, total_pairs)

    def _compute_window_balance_factor(
        self,
        windows: List[WindowDefinition],
        observation_metadata: Optional[Dict[str, Any]] = None,
        metric_dataframe: Optional[MetricDataFrame] = None,
    ) -> float:
        """Compute f₄: 1.0 - min(1.0, std_size / mean_size)

        Enhanced with observation counts when available.

        Args:
            windows: List of window definitions
            observation_metadata: Optional observation metadata from evidence package
            metric_dataframe: Optional metric dataframe with per-window observation counts

        Returns:
            Window balance factor in [0, 1]
        """
        if not windows:
            return 0.0

        # Try to use observation counts first
        if observation_metadata and observation_metadata.get("per_window_observations"):
            per_window_obs = observation_metadata["per_window_observations"]
            if per_window_obs:
                window_sizes: List[float] = []
                for window in windows:
                    window_id = getattr(window, "window_id", None)
                    if window_id and window_id in per_window_obs:
                        obs_data = per_window_obs[window_id]
                        if isinstance(obs_data, dict) and "count" in obs_data:
                            window_sizes.append(float(obs_data["count"]))

                if window_sizes:
                    return compute_balance_factor(window_sizes)

        # Fallback: compute from metric_dataframe observation counts
        if metric_dataframe and metric_dataframe.metrics:
            window_ids = [w.window_id for w in windows]
            obs_counts: List[float] = []
            for window_id in window_ids:
                window_obs_count = 0
                for metric_series in metric_dataframe.metrics.values():
                    if isinstance(metric_series, dict) and window_id in metric_series:
                        value_list = metric_series[window_id]
                        if isinstance(value_list, list):
                            window_obs_count += len([v for v in value_list if v is not None])
                obs_counts.append(float(window_obs_count))
            if obs_counts and any(c > 0 for c in obs_counts):
                return compute_balance_factor(obs_counts)

        # Final fallback to commit count proxy
        window_sizes = [float(w.commits) for w in windows]
        return compute_balance_factor(window_sizes)

    def _compute_detector_success_factor(
        self,
        detector_results: DetectorResults,
        metric_dataframe: MetricDataFrame,
        evidence_package: Optional[EvidencePackage] = None,
    ) -> float:
        """Compute f₅: successful_runs / total_attempts

        Enhanced with detector execution metadata when available.

        Args:
            detector_results: Container for detector outputs
            metric_dataframe: Container for extracted metrics
            evidence_package: Optional evidence package with observation-level metadata

        Returns:
            Detector success factor in [0, 1]
        """
        if not detector_results.detector_outputs:
            return 0.0

        num_detectors = len(detector_results.detector_outputs)
        num_metrics = len(metric_dataframe.metrics) if metric_dataframe.metrics else 0

        if num_detectors == 0 or num_metrics == 0:
            return 0.0

        # Try to use detector execution metadata first
        if evidence_package and hasattr(evidence_package, "detector_execution_metadata"):
            exec_metadata = evidence_package.detector_execution_metadata
            if exec_metadata:
                successful_runs = 0
                total_attempts = 0

                for det_id, det_data in exec_metadata.items():
                    if isinstance(det_data, dict):
                        success = det_data.get("success", False)
                        execution_count = det_data.get("execution_count", 0)

                        if success:
                            successful_runs += execution_count
                        total_attempts += execution_count

                if total_attempts > 0:
                    return compute_detector_success_factor(successful_runs, total_attempts)
                # If no execution metadata, assume success
                return 1.0

        # Fallback to detector_results-based calculation
        total_attempts = num_metrics * num_detectors
        successful_runs = 0

        for det_id, det_data in detector_results.detector_outputs.items():
            if isinstance(det_data, dict):
                status = det_data.get("status", "executed")
                if status in ("error", "skipped"):
                    # Detector failed — count as unsuccessful for all metrics
                    continue
                # Detector ran (whether it found something or not)
                successful_runs += num_metrics

        return compute_detector_success_factor(successful_runs, total_attempts)

    def _compute_observation_quality_factor(
        self,
        observation_metadata: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Compute f₆: observation quality factor (IMS Phase 4 extension).

        Quality = (complete + 0.5*partial) / (complete + partial + estimated)

        Args:
            observation_metadata: Optional observation metadata from evidence package

        Returns:
            Observation quality factor in [0, 1]
        """
        if not observation_metadata:
            return 1.0

        quality = observation_metadata.get("observation_quality", {})
        if not quality:
            return 1.0

        complete = quality.get("complete", 0)
        partial = quality.get("partial", 0)
        estimated = quality.get("estimated", 0)

        return compute_observation_quality_factor(complete, partial, estimated)
