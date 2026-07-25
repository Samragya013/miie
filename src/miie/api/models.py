"""Pydantic request/response models for the MIIE REST API.

Mirrors the frozen schemas in ACS v1.0 §14 and TFS §14.3.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    """POST /v1/analyze request body (TFS §14.3)."""

    repo: str = Field(..., min_length=1, max_length=2048, description="Repository path or URL")
    since: Optional[str] = Field(None, description="ISO 8601 start date")
    until: Optional[str] = Field(None, description="ISO 8601 end date")
    metrics: List[str] = Field(default_factory=lambda: ["M-02", "M-06"])
    window_strategy: str = Field(default="time", pattern="^(time|commit|release|custom)$")
    window_size: int = Field(default=7, ge=1)
    detectors: List[str] = Field(default_factory=lambda: ["D-01", "D-02", "D-03"])
    output_formats: List[str] = Field(default_factory=lambda: ["json", "md"])
    exclude_bots: bool = False
    thresholds: Dict[str, Any] = Field(default_factory=dict)
    detector_weights: Dict[str, float] = Field(default_factory=lambda: {"D-01": 0.40, "D-02": 0.35, "D-03": 0.25})
    seed: int = 42
    output_dir: str = Field(default="./output", max_length=1024)


class BenchmarkRequest(BaseModel):
    """POST /v1/benchmark request body (TFS §14.3)."""

    suite: str = Field(..., min_length=1, description="Benchmark suite ID")
    detectors: List[str] = Field(default_factory=lambda: ["D-01", "D-02", "D-03"])
    config_overrides: Dict[str, Any] = Field(default_factory=dict)
    seed: int = 42
    output_formats: List[str] = Field(default_factory=lambda: ["json", "md"])


class ExplainRequest(BaseModel):
    """POST /v1/explain request body (TFS §14.3)."""

    job_id: str = Field(..., min_length=1, description="Job ID of completed analysis")
    metric: Optional[str] = Field(None, description="Specific metric to explain")
    detector: Optional[str] = Field(None, description="Specific detector to explain")
    format: str = Field(default="json", pattern="^(md|json)$")


class ExportRequest(BaseModel):
    """POST /v1/export request body (TFS §14.3)."""

    job_id: str = Field(..., min_length=1, description="Job ID of completed analysis")
    formats: List[str] = Field(default_factory=lambda: ["json", "md", "csv"])
    filter: Optional[str] = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class JobAccepted(BaseModel):
    """202 response for async job creation (TFS §14.3)."""

    job_id: str
    status: str
    poll_url: str


class JobStatusResponse(BaseModel):
    """GET /v1/jobs/{job_id} response when running (TFS §14.3)."""

    job_id: str
    status: str
    progress: float = Field(0.0, ge=0.0, le=1.0)
    stage: Optional[str] = None


class JobCompletedResponse(BaseModel):
    """GET /v1/jobs/{job_id} response when completed (TFS §14.3)."""

    job_id: str
    status: str
    created_at: str
    completed_at: str
    results_url: str
    summary: Dict[str, Any]


class HealthResponse(BaseModel):
    """GET /v1/health response (TFS §14.3)."""

    status: str
    version: str
    uptime_seconds: float


class ExportResponse(BaseModel):
    """POST /v1/export response (TFS §14.3)."""

    download_urls: Dict[str, str]


class ExplainResponse(BaseModel):
    """POST /v1/explain response (TFS §14.3)."""

    explanation: str
    rule_fired: str
    evidence_refs: List[str]
    metric: str
    detector: str


# ---------------------------------------------------------------------------
# RFC 7807 Problem Details
# ---------------------------------------------------------------------------


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details error response (ACS v1.0 §4.4, TFS §14.5)."""

    type: str
    title: str
    status: int
    detail: str
    instance: str
