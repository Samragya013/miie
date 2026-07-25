"""Application Service — central coordinator for MIIE application layer.

The ApplicationService is the single entry point that the CLI/API
use to execute analysis workflows. It owns:

- Pipeline orchestration (delegates to processing layer)
- Workflow management (delegates to WorkflowEngine)
- Session lifecycle (delegates to SessionManager)
- Output formatting (delegates to OutputFormatter)

The service contains NO scientific logic. It instantiates engines
from the processing layer and delegates execution to them. All
scoring, detection, evidence, and explanation logic lives in the
frozen processing layer.
"""

from __future__ import annotations

import json as _json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .output import DETECTOR_NAMES, METRIC_NAMES, FormattedOutput, OutputFormatter
from .router import CommandRouter
from .session import SessionManager
from .workflow import WorkflowEngine, WorkflowResult, WorkflowStep


def _default_detector_registry():
    """Create and populate the default detector registry."""
    from ..processing.detection.correlation_breakdown_detector import (
        CorrelationBreakdownDetector,
    )
    from ..processing.detection.distribution_drift_detector import (
        DistributionDriftDetector,
    )
    from ..processing.detection.registry import DetectorRegistry
    from ..processing.detection.threshold_compression_detector import (
        ThresholdCompressionDetector,
    )

    registry = DetectorRegistry()
    registry.register(DistributionDriftDetector())
    registry.register(CorrelationBreakdownDetector())
    registry.register(ThresholdCompressionDetector())
    return registry


def _resolve_auth_token(auth_token: Optional[str] = None) -> Optional[str]:
    """Resolve auth token from argument or environment."""
    import os

    return auth_token or os.environ.get("GITHUB_TOKEN")


class ApplicationService:
    """Central coordinator for the MIIE application layer.

    Usage:
        service = ApplicationService()
        result = service.analyze(repo_path="./my-repo")
        print(result)
    """

    def __init__(self) -> None:
        self.session_manager = SessionManager()
        self.workflow_engine = WorkflowEngine()
        self.command_router = CommandRouter()
        self.output = OutputFormatter()

    def analyze(
        self,
        repo_path: str,
        metrics: Optional[List[str]] = None,
        detectors: Optional[List[str]] = None,
        output_dir: str = "./output",
        window_strategy: str = "time",
        window_size: int = 7,
        since: Optional[str] = None,
        until: Optional[str] = None,
        exclude_bots: bool = False,
        thresholds: Optional[str] = None,
        dry_run: bool = False,
        seed: int = 42,
        formats: Optional[List[str]] = None,
        auth_token: Optional[str] = None,
        forensic: bool = False,
        verbose: bool = False,
    ) -> FormattedOutput:
        """Execute the full analysis pipeline.

        This method orchestrates all 7 pipeline stages by delegating
        to the frozen processing engines. The scientific logic is never
        modified — only consumed through public interfaces.
        """
        if metrics is None:
            metrics = ["M-02", "M-06"]
        if detectors is None:
            detectors = ["D-01", "D-02", "D-03"]
        if formats is None:
            formats = ["json"]

        # Parse thresholds
        detector_config = None
        if thresholds:
            try:
                detector_config = _json.loads(thresholds)
            except _json.JSONDecodeError as exc:
                return self.output.format_error(f"--thresholds must be valid JSON: {exc}")

        resolved_token = _resolve_auth_token(auth_token)

        # Dry run
        if dry_run:
            return self._dry_run(
                repo_path=repo_path,
                metrics=metrics,
                detectors=detectors,
                window_strategy=window_strategy,
                window_size=window_size,
                output_dir=output_dir,
            )

        # Create session
        self.session_manager.create(
            repo_path=repo_path,
            output_dir=output_dir,
            verbose=verbose,
            seed=seed,
        )
        self.session_manager.record_command("analyze", {"repo_path": repo_path})

        # Execute pipeline stages
        t_total = time.perf_counter()
        timings: Dict[str, float] = {}

        try:
            # Stage 1: Acquisition
            t1 = time.perf_counter()
            from ..processing.ingestion import RepositoryIngestionEngine

            ingestion = RepositoryIngestionEngine(auth_token=resolved_token)
            repository_context = ingestion.ingest(repo_path=repo_path, shallow_depth=None)
            if not ingestion.validate(repository_context):
                return self.output.format_error("Repository context validation failed")
            timings["acquisition"] = time.perf_counter() - t1

            total_commits = getattr(repository_context, "total_commits", "?")
            contributor_count = getattr(repository_context, "contributor_count", "?")

            # Stage 2: Validation
            t2 = time.perf_counter()
            timings["validation"] = time.perf_counter() - t2

            # Stage 3: Extraction (observation path — preserves per-commit data)
            t3 = time.perf_counter()
            from ..processing.extraction.engine import ExtractionEngine

            extraction = ExtractionEngine()
            since_dt = datetime.fromisoformat(since) if since else None
            until_dt = datetime.fromisoformat(until) if until else None
            observation_collection, metric_dataframe = extraction.extract(
                context=repository_context,
                metric_list=list(metrics),
                since=since_dt,
                until=until_dt,
                exclude_bots=exclude_bots,
                seed=seed,
            )
            metric_names = list(getattr(metric_dataframe, "metrics", {}).keys()) if metric_dataframe else list(metrics)
            timings["extraction"] = time.perf_counter() - t3

            # Stage 4: Windowing via ObservationWindowBuilder
            t4 = time.perf_counter()
            from ..processing.observation.models import WindowConfig
            from ..processing.observation.window_builder import ObservationWindowBuilder

            strategy_map = {"time": "temporal", "commit": "commit_count", "release": "temporal", "custom": "custom"}
            obs_strategy = strategy_map.get(window_strategy, "temporal")
            window_config = WindowConfig(
                strategy=obs_strategy,
                window_size=window_size,
                min_observations=2,
            )
            builder = ObservationWindowBuilder()
            builder_result = builder.build(collection=observation_collection, config=window_config)
            observation_windows = builder_result.windows
            window_count = len(observation_windows)
            timings["segmentation"] = time.perf_counter() - t4

            if window_count < 2:
                msg = f"Insufficient windows: {window_count} (need >= 2). Adjust --window-size or time range."
                return self.output.format_warning(msg)

            # Convert observation windows to legacy WindowDefinitions for scoring/evidence
            from ..schemas.models import WindowDefinition

            windows = []
            for ow in observation_windows:
                wd = WindowDefinition(
                    window_id=ow.window_id,
                    start_date=ow.start_boundary[:10] if hasattr(ow, "start_boundary") and ow.start_boundary else None,
                    end_date=ow.end_boundary[:10] if hasattr(ow, "end_boundary") and ow.end_boundary else None,
                    commits=len(ow.observations) if hasattr(ow, "observations") else 0,
                    strategy=obs_strategy,
                    size_config={"size": window_size},
                )
                windows.append(wd)

            # Stage 5: Detection (observation path — detectors see full per-commit distributions)
            t5 = time.perf_counter()
            from ..processing.detection.dispatcher import DetectorDispatcherEngine

            registry = _default_detector_registry()
            dispatcher = DetectorDispatcherEngine(registry)
            detector_results = dispatcher.invoke_observations(
                observation_windows=observation_windows,
                detector_config=detector_config,
                enabled_detectors=list(detectors),
            )
            timings["detection"] = time.perf_counter() - t5

            # Stage 6: Scoring + Evidence
            t6 = time.perf_counter()
            from ..processing.evidence import EvidenceEngine
            from ..processing.explanation.engine import ExplanationEngine
            from ..processing.scoring.engine import ScoringEngine

            scoring = ScoringEngine()
            score_package = scoring.compute_integrity_score(
                detector_results=detector_results,
                metric_dataframe=metric_dataframe,
                windows=windows,
            )
            evidence_engine = EvidenceEngine()
            evidence_package = evidence_engine.generate(
                repository_context=repository_context,
                metric_dataframe=metric_dataframe,
                windows=windows,
                detector_results=detector_results,
                score_package=score_package,
                configuration={
                    "metric_list": list(metrics),
                    "since": since_dt,
                    "until": until_dt,
                    "exclude_bots": exclude_bots,
                    "segmentation_strategy": window_strategy,
                    "segmentation_size": window_size,
                },
            )
            explanation_engine = ExplanationEngine()
            explanation_report = explanation_engine.generate(
                evidence_package=evidence_package,
                score_package=score_package,
            )
            timings["evidence"] = time.perf_counter() - t6

            # Stage 7: Reporting
            t7 = time.perf_counter()
            from ..processing.reporting.engine import ReportGenerator

            analysis_results = {
                "repository_context": repository_context,
                "metric_dataframe": metric_dataframe,
                "windows": windows,
                "detector_results": detector_results,
                "score_package": score_package,
                "evidence_package": evidence_package,
                "explanation_report": explanation_report,
            }
            report_generator = ReportGenerator()
            report_generator.generate(
                analysis_result=analysis_results,
                output_formats=list(formats),
                output_dir=Path(output_dir),
            )
            timings["reporting"] = time.perf_counter() - t7

            timings["total"] = time.perf_counter() - t_total

            # Extract scores
            integrity = score_package.integrity
            confidence = score_package.confidence
            integrity_overall = integrity.get("overall", 0.0) if isinstance(integrity, dict) else integrity.overall
            confidence_overall = confidence.get("overall", 0.0) if isinstance(confidence, dict) else confidence.overall

            # Extract detector outputs
            detector_outputs = {}
            if detector_results:
                detector_outputs = getattr(detector_results, "detector_outputs", {})
                if not detector_outputs and hasattr(detector_results, "d_01"):
                    detector_outputs = {
                        "D-01": getattr(detector_results, "d_01", {}),
                        "D-02": getattr(detector_results, "d_02", {}),
                        "D-03": getattr(detector_results, "d_03", {}),
                    }

            # Format output
            result = self.output.format_analysis_result(
                integrity_score=integrity_overall,
                confidence_score=confidence_overall,
                detector_outputs=detector_outputs,
                metric_names=metric_names,
                window_count=window_count,
                total_commits=total_commits,
                contributor_count=contributor_count,
                timings=timings,
                verbose=verbose,
            )

            # Cache result
            self.session_manager.cache_result(
                f"analyze:{repo_path}",
                result.json_data or {},
            )

            return result

        except Exception as exc:
            return self.output.format_error(
                f"Analysis failed: {exc}",
                details=str(exc) if verbose else None,
            )

    def detect(
        self,
        repo_path: str,
        metrics: Optional[List[str]] = None,
        detectors: Optional[List[str]] = None,
        seed: int = 42,
        auth_token: Optional[str] = None,
    ) -> FormattedOutput:
        """Execute detection only (no scoring/evidence)."""
        if metrics is None:
            metrics = ["M-02", "M-06"]
        if detectors is None:
            detectors = ["D-01", "D-02", "D-03"]

        resolved_token = _resolve_auth_token(auth_token)

        try:
            from ..processing.detection.dispatcher import DetectorDispatcherEngine
            from ..processing.extraction import MetricExtractionEngine
            from ..processing.ingestion import RepositoryIngestionEngine
            from ..processing.segmentation import WindowSegmentationEngine

            ingestion = RepositoryIngestionEngine(auth_token=resolved_token)
            repository_context = ingestion.ingest(repo_path=repo_path, shallow_depth=None)

            extraction = MetricExtractionEngine()
            metric_dataframe = extraction.extract(
                context=repository_context,
                metric_list=list(metrics),
            )

            segmentation = WindowSegmentationEngine()
            windows = segmentation.segment(
                metric_dataframe=metric_dataframe,
                strategy="time",
                size=7,
                repository_context=repository_context,
            )

            registry = _default_detector_registry()
            dispatcher = DetectorDispatcherEngine(registry)
            detector_results = dispatcher.invoke(
                metric_dataframe=metric_dataframe,
                windows=windows,
                enabled_detectors=list(detectors),
            )

            # Extract detector outputs
            detector_outputs = {}
            if detector_results:
                detector_outputs = getattr(detector_results, "detector_outputs", {})

            return self.output.format_analysis_result(
                integrity_score=0.0,
                confidence_score=0.0,
                detector_outputs=detector_outputs,
                metric_names=metrics,
                window_count=len(windows),
                total_commits=getattr(repository_context, "total_commits", "?"),
                contributor_count=getattr(repository_context, "contributor_count", "?"),
            )

        except Exception as exc:
            return self.output.format_error(f"Detection failed: {exc}")

    def validate(
        self,
        target: str,
        validation_type: str = "config",
    ) -> FormattedOutput:
        """Validate a config file or analysis output."""
        try:
            path = Path(target)
            if not path.exists():
                return self.output.format_error(f"File not found: {target}")

            if validation_type == "config":
                from ..contracts.validators import (
                    validate_config_file,  # type: ignore[attr-defined]
                )

                validate_config_file(str(path))
                return self.output.format_warning(f"Config validated: {target}")
            elif validation_type == "analysis":
                _json.loads(path.read_text())  # Validate JSON structure
                return self.output.format_warning(f"Analysis output validated: {target}")
            else:
                return self.output.format_error(f"Unknown validation type: {validation_type}")

        except Exception as exc:
            return self.output.format_error(f"Validation failed: {exc}")

    def status(self, version: str = "unknown") -> FormattedOutput:
        """Show system status."""
        return self.output.format_status(
            version=version,
            detectors=list(DETECTOR_NAMES.keys()),
            metrics=list(METRIC_NAMES.keys()),
        )

    def execute_workflow(
        self,
        steps: List[Tuple[str, str, str, Callable]],
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkflowResult:
        """Execute a workflow with the given steps.

        Each step is a tuple of (step_id, name, description, handler).
        """
        workflow_steps = [
            WorkflowStep(
                step_id=sid,
                name=name,
                description=desc,
                handler=handler,
                order=i,
            )
            for i, (sid, name, desc, handler) in enumerate(steps)
        ]
        self.workflow_engine.define(workflow_steps, context)
        return self.workflow_engine.execute()

    def _dry_run(
        self,
        repo_path: str,
        metrics: List[str],
        detectors: List[str],
        window_strategy: str,
        window_size: int,
        output_dir: str,
    ) -> FormattedOutput:
        """Generate a dry-run plan without executing."""
        lines = [
            f"  Repository:     {repo_path}",
            f"  Metrics:        {', '.join(metrics)}",
            f"  Detectors:      {', '.join(detectors)}",
            f"  Window:         {window_strategy} (size={window_size})",
            f"  Output:         {output_dir}",
            "",
            "  Stages to execute:",
            "    1. Repository Acquisition",
            "    2. Repository Validation",
            "    3. Metric Extraction",
            "    4. Window Segmentation",
            "    5. Detector Execution",
            "    6. Scoring + Evidence Generation",
            "    7. Report Generation",
        ]
        return FormattedOutput(
            sections=[("Dry Run — Analysis Plan", "\n".join(lines))],
            exit_code=0,
        )
