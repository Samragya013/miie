"""Job storage and background task runner for the MIIE REST API.

V1 uses an in-memory dict for job state. Future versions can swap
this for filesystem-backed or database-backed storage.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .models import AnalyzeRequest, BenchmarkRequest

logger = logging.getLogger(__name__)


class JobStore:
    """In-memory job storage (V1) with LRU eviction at 200 jobs."""

    MAX_JOBS = 200

    def __init__(self) -> None:
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._insertion_order: list[str] = []

    def create_job(self, job_type: str, params: Dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            # LRU eviction when at capacity
            while len(self._jobs) >= self.MAX_JOBS:
                oldest_id = self._insertion_order.pop(0)
                self._jobs.pop(oldest_id, None)
                logger.debug("Evicted oldest job %s (capacity %d)", oldest_id, self.MAX_JOBS)
            self._jobs[job_id] = {
                "job_id": job_id,
                "job_type": job_type,
                "params": params,
                "status": "created",
                "progress": 0.0,
                "stage": None,
                "created_at": now,
                "completed_at": None,
                "result": None,
                "error": None,
            }
            self._insertion_order.append(job_id)
        return job_id

    def update_status(
        self,
        job_id: str,
        status: str,
        progress: float = 0.0,
        stage: Optional[str] = None,
    ) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = status
                self._jobs[job_id]["progress"] = progress
                if stage is not None:
                    self._jobs[job_id]["stage"] = stage

    def set_result(self, job_id: str, result: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "completed"
                self._jobs[job_id]["progress"] = 1.0
                self._jobs[job_id]["stage"] = None
                self._jobs[job_id]["result"] = result
                self._jobs[job_id]["completed_at"] = now

    def set_error(self, job_id: str, error: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = error
                self._jobs[job_id]["completed_at"] = now

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                return dict(job)  # Return a copy to prevent external mutation
            return None

    def exists(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._jobs


def _run_analyze_job(job_id: str, request: AnalyzeRequest) -> None:
    """Background worker for POST /v1/analyze."""
    store = get_job_store()
    temp_dir = None
    try:
        # Validate repo path — prevent path traversal
        raw_repo = request.repo.strip()
        if ".." in raw_repo or re.search(r"[<>\"|?*]", raw_repo):
            store.set_error(
                job_id,
                {
                    "type": "https://miie.dev/errors/invalid-repo",
                    "title": "Invalid Repository Path",
                    "status": 400,
                    "detail": "Repository path contains invalid characters or traversal sequences.",
                },
            )
            return
        repo_path = Path(raw_repo).resolve()
        if not repo_path.exists() or not repo_path.is_dir():
            store.set_error(
                job_id,
                {
                    "type": "https://miie.dev/errors/invalid-repo",
                    "title": "Invalid Repository Path",
                    "status": 400,
                    "detail": f"Repository path not found or is not a directory: {raw_repo}",
                },
            )
            return
        # Validate output_dir — prevent path traversal
        raw_output = request.output_dir.strip()
        if ".." in raw_output or re.search(r"[<>\"|?*]", raw_output):
            store.set_error(
                job_id,
                {
                    "type": "https://miie.dev/errors/invalid-output-dir",
                    "title": "Invalid Output Directory",
                    "status": 400,
                    "detail": "Output directory contains invalid characters or traversal sequences.",
                },
            )
            return
        output_path = Path(raw_output).resolve()
        # Block writes to sensitive system directories
        sensitive_output = {"/etc", "/proc", "/sys", "/dev", "/bin", "/sbin", "/usr"}
        if any(str(output_path).startswith(s) for s in sensitive_output):
            store.set_error(
                job_id,
                {
                    "type": "https://miie.dev/errors/invalid-output-dir",
                    "title": "Invalid Output Directory",
                    "status": 400,
                    "detail": "Output directory points to a restricted system directory.",
                },
            )
            return
        # Block access to sensitive system directories (Windows + Linux)
        home = Path.home()
        sensitive = {
            "/etc",
            "/proc",
            "/sys",
            "/dev",
            str(home / ".ssh"),
            str(home / ".aws"),
            str(home / ".gcp"),
            str(home / ".azure"),
            str(home / ".kube"),
            str(Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Credentials"),
            str(Path(os.environ.get("USERPROFILE", "")) / ".ssh"),
            str(Path(os.environ.get("USERPROFILE", "")) / ".aws"),
        }
        if any(str(repo_path).startswith(s) for s in sensitive if s):
            store.set_error(
                job_id,
                {
                    "type": "https://miie.dev/errors/invalid-repo",
                    "title": "Invalid Repository Path",
                    "status": 400,
                    "detail": "Repository path points to a restricted system directory.",
                },
            )
            return
        store.update_status(job_id, "running", progress=0.1, stage="ingestion")

        from ..processing.detection.dispatcher import DetectorDispatcherEngine
        from ..processing.detection.registry import DetectorRegistry
        from ..processing.evidence import EvidenceEngine
        from ..processing.explanation.engine import ExplanationEngine
        from ..processing.extraction import MetricExtractionEngine
        from ..processing.ingestion import RepositoryIngestionEngine
        from ..processing.scoring.engine import ScoringEngine
        from ..processing.segmentation import WindowSegmentationEngine

        registry = DetectorRegistry()
        from ..processing.detection.correlation_breakdown_detector import (
            CorrelationBreakdownDetector,
        )
        from ..processing.detection.distribution_drift_detector import (
            DistributionDriftDetector,
        )
        from ..processing.detection.threshold_compression_detector import (
            ThresholdCompressionDetector,
        )

        registry.register(DistributionDriftDetector())
        registry.register(CorrelationBreakdownDetector())
        registry.register(ThresholdCompressionDetector())

        ingestion = RepositoryIngestionEngine()
        extraction = MetricExtractionEngine()
        segmentation = WindowSegmentationEngine()
        detection = DetectorDispatcherEngine(registry)
        scoring = ScoringEngine()
        evidence = EvidenceEngine()
        explanation = ExplanationEngine()

        store.update_status(job_id, "running", progress=0.2, stage="ingestion")
        ctx = ingestion.ingest(repo_path=request.repo)

        store.update_status(job_id, "running", progress=0.35, stage="extraction")
        since_dt = datetime.fromisoformat(request.since) if request.since else None
        until_dt = datetime.fromisoformat(request.until) if request.until else None
        mdf = extraction.extract(
            ctx,
            request.metrics,
            since=since_dt,
            until=until_dt,
            exclude_bots=request.exclude_bots,
        )

        store.update_status(job_id, "running", progress=0.5, stage="segmentation")
        wins = segmentation.segment(mdf, strategy=request.window_strategy, size=request.window_size)

        store.update_status(job_id, "running", progress=0.65, stage="detection")
        det_results = detection.invoke(mdf, wins, enabled_detectors=request.detectors)

        store.update_status(job_id, "running", progress=0.75, stage="scoring")
        score_pkg = scoring.compute_integrity_score(det_results, mdf, wins, detector_weights=request.detector_weights)

        store.update_status(job_id, "running", progress=0.85, stage="evidence")
        ev_pkg = evidence.generate(ctx, mdf, wins, det_results, score_pkg, {"seed": request.seed})

        store.update_status(job_id, "running", progress=0.95, stage="explanation")
        expl = explanation.generate(ev_pkg, score_pkg)

        score_data = score_pkg
        result = {
            "repo_id": ctx.repo_id,
            "integrity_overall": score_data.integrity.overall,
            "confidence_overall": score_data.confidence.overall,
            "integrity_per_metric": score_data.integrity.per_metric,
            "explanations_count": len(expl.explanations),
        }
        store.set_result(job_id, result)

    except Exception:
        logger.exception("Analysis job %s failed", job_id)
        store.set_error(
            job_id,
            {
                "type": "https://miie.dev/errors/analysis-failed",
                "title": "Analysis Failed",
                "status": 500,
                "detail": "Analysis failed. Check server logs for details.",
            },
        )
    finally:
        # Cleanup temp directories created during analysis
        if temp_dir is not None:
            import shutil

            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                logger.debug("Failed to clean up temp dir %s", temp_dir)


def _run_benchmark_job(job_id: str, request: BenchmarkRequest) -> None:
    """Background worker for POST /v1/benchmark."""
    store = get_job_store()
    temp_dir = None
    try:
        store.update_status(job_id, "running", progress=0.2, stage="benchmark")

        from ..processing.benchmark.engine import BenchmarkEngine

        engine = BenchmarkEngine()
        result_obj = engine.execute(
            suite_id=request.suite,
            detector_ids=request.detectors,
            config=request.config_overrides,
            seed=request.seed,
        )

        result = {
            "suite_id": (result_obj.suite_id if hasattr(result_obj, "suite_id") else request.suite),
            "metadata": result_obj.metadata if hasattr(result_obj, "metadata") else {},
        }
        store.set_result(job_id, result)

    except Exception:
        logger.exception("Benchmark job %s failed", job_id)
        store.set_error(
            job_id,
            {
                "type": "https://miie.dev/errors/benchmark-failed",
                "title": "Benchmark Failed",
                "status": 500,
                "detail": "Benchmark failed. Check server logs for details.",
            },
        )
    finally:
        if temp_dir is not None:
            import shutil

            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                logger.debug("Failed to clean up temp dir %s", temp_dir)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_job_store: Optional[JobStore] = None
_store_lock = threading.Lock()

# Thread pool for background jobs (M6: prevent unbounded thread creation)
_job_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="miie-job")


def get_job_store() -> JobStore:
    global _job_store
    if _job_store is None:
        with _store_lock:
            if _job_store is None:
                _job_store = JobStore()
    return _job_store


_start_time: float = time.time()


def get_uptime() -> float:
    return time.time() - _start_time
