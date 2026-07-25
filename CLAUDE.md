# MIIE -- Repository Constitution

## Purpose

MIIE (Measurement Integrity Intelligence Engine) is a Python research tool that evaluates the validity and integrity of software engineering metrics extracted from VCS histories. It detects distribution drift, correlation breakdown, and threshold compression using statistical methods.

**This is the single source of truth for repository structure, conventions, and constraints.**

## Quick Reference

- **Version**: 1.6.1
- **Python**: 3.10-3.13
- **Platform**: **Windows-only** (no Linux/macOS CI, no cross-platform guarantees)
- **Package**: `miie` (src layout: `src/miie/`)
- **CLI**: `miie` (entry: `miie.cli:cli`)
- **API**: `miie-api` (FastAPI, entry: `miie.api.server:main`)
- **Tests**: `pytest` (2849+ tests, all passing, 6 skipped)
- **CI**: ALL 10 JOBS GREEN (lint, typecheck, unit-tests x4, integration-tests, regression, detector-regression, security)
- **Formatting**: black (120), isort, flake8, mypy

## Architecture

```
src/miie/
├── api/                    # FastAPI REST endpoints (6 frozen)
├── application/            # CLI interactive layer, workflow, session
├── benchmark/              # Benchmark execution engine
├── cli/                    # Click CLI commands (14 commands)
├── config/                 # Configuration loader
├── contracts/              # Interfaces (frozen contracts)
├── experimental/           # Non-production code
├── metrics/                # Metric extraction (M-01 through M-07)
├── observation_graph/      # Observation graph data structures
├── orchestration/          # Workflow orchestration
├── processing/             # Core scientific processing
│   ├── benchmark/          # Benchmark evaluation
│   ├── detection/          # Detectors (D-01, D-02, D-03)
│   ├── evaluation/         # Evaluation engine
│   ├── explanation/        # Explanation engine with recommendations
│   ├── extraction/         # Data extraction
│   ├── observation/        # Observation processing
│   ├── reporting/          # Report generation (14+ types)
│   └── scoring/            # Integrity + Confidence scoring
├── providers/              # External data providers
├── reporting/              # Legacy reporting (templates)
├── sampling/               # Sampling strategies
├── schemas/                # Data models (frozen)
├── scientific/             # Scientific validation
├── storage/                # Storage interfaces
├── utils/                  # Utilities (hashing, etc.)
├── validation/             # Validation framework
└── workspace/              # Persistent workspace (ECP-03)
    ├── engine.py           # WorkspaceEngine, WorkspaceState
    ├── views.py            # 11 view classes
    ├── traceability.py     # Scientific traceability
    ├── recommendations.py  # Deterministic recommendations
    ├── comparison.py       # Session comparison
    ├── persistence.py      # Save/load workspace
    └── export.py           # Multi-format export
```

## Frozen Core (DO NOT MODIFY)

The following are frozen scientific contracts. Do not change their logic, interfaces, or outputs:

- **Metrics**: M-01 through M-07 (extraction in `metrics/`)
- **Detectors**: D-01 (Distributional Drift), D-02 (Correlation Breakdown), D-03 (Threshold Compression) in `processing/detection/`
- **Evidence**: EvidencePackage with observation-level provenance in `processing/evidence.py`
- **Confidence**: ConfidenceScore in `schemas/models.py`
- **Integrity Score**: IntegrityScore in `schemas/models.py`
- **Statistical methods**: `processing/detection/statistics.py`
- **WorkflowEngine**: `application/workflow.py`
- **SessionManager**: `application/session.py`
- **ApplicationService**: `application/service.py`
- **All contracts**: `contracts/interfaces.py`

## Allowed Dependencies

```
contracts → (no internal deps)
schemas → contracts
processing → contracts, schemas
metrics → contracts, schemas, utils
application → contracts, schemas, processing, metrics, workspace
workspace → schemas, processing (read-only consumption)
api → application, schemas
cli → application
```

## Workflow Engine (Application Layer)

- **WorkflowEngine**: Drives the analysis pipeline
- **InteractiveNavigator**: Interactive menu system with workspace integration
- **NavigationState**: 10 states (MAIN_MENU through WORKSPACE_VIEW)
- **MenuAction**: 13 actions (SELECT, BACK, QUIT, HELP, CANCEL, CONFIRM, WORKFLOW, VIEW_RESULTS, EXPORT, CONFIG, EXIT, EXPLORE, NEW)
- **OutputFormatter**: 4 output sections only (RESULTS, INSIGHTS, ACTIONS, NEXT_STEPS)

## Workspace (ECP-03)

The workspace package (`src/miie/workspace/`) provides post-analysis persistent state:

- **WorkspaceEngine**: Manages WorkspaceState, initializes from WorkflowResult
- **WorkspaceState**: Dataclass holding all analysis results, navigation state, bookmarks
- **Views**: ExecutiveSummary, MetricView, DetectorView, EvidenceView, ConfidenceView, IntegrityView, ValidationView, BenchmarkView, RecommendationView, SessionInfoView, WorkspaceOverview
- **TraceabilityEngine**: Scientific traceability (conclusion → evidence → detector → metric → observation)
- **RecommendationEngine**: Deterministic recommendations from scientific outputs
- **ComparisonEngine**: Session comparison
- **WorkspacePersistence**: Save/load workspace state
- **WorkspaceExporter**: Multi-format export (JSON, Markdown, CSV)

## API Endpoints (6 frozen per TFS 14.3)

- `GET /v1/health` -- Service health
- `POST /v1/analyze` -- Analysis job
- `POST /v1/benchmark` -- Benchmark job
- `POST /v1/explain` -- Explanation generation
- `POST /v1/export` -- Result export
- `GET /v1/jobs/{job_id}` -- Job status

## CLI Commands (10)

- `miie analyze` -- Full analysis pipeline
- `miie ingest` -- Validate and ingest a repository
- `miie detect` -- Run detectors on a repository
- `miie benchmark` -- Execute a benchmark suite
- `miie evaluate` -- Evaluate benchmark results
- `miie explain` -- Generate explanations
- `miie export` -- Export results
- `miie generate` -- Generate synthetic candidates
- `miie status` -- Show system status
- `miie validate` -- Validate config/output

## Report Types (14+)

Executive summary, detailed analysis, benchmark, comparison, traceability, recommendation, evidence, detector, metric, export manifest, integrity, confidence, validation, workspace overview

## Testing

- **Framework**: pytest
- **Count**: 2758 tests (all passing)
- **Run**: `pytest`
- **Architecture tests**: `tests/architecture/` (layer dependency, package structure)
- **Coverage**: pytest-cov available

## Code Quality

- **Formatting**: `black --line-length 120`
- **Import sorting**: `isort --profile black`
- **Linting**: `flake8` + `flake8-bugbear`
- **Type checking**: `mypy` (strict mode available)
- **Pre-commit hooks**: `.pre-commit-config.yaml`

## Key Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Poetry config, build, dependencies |
| `Makefile` | lint/typecheck/test targets |
| `setup.cfg` | flake8/mypy/pytest config |
| `.pre-commit-config.yaml` | Pre-commit hooks |
| `CHANGELOG.md` | Keep-a-Changelog format |
| `README.md` | User-facing documentation |
| `docs/` | 200+ documentation files |
| `tests/` | Test suite |
| `benchmarks/` | Benchmark results + cloned repos |
| `reports/` | Generated analysis reports |
| `archive/` | Historical code and outputs |
| `schemas/` | YAML/JSON schema definitions |
| `scripts/` | Development scripts (gitignored) |

## Development Rules

1. **No modifications to frozen core** -- metrics, detectors, evidence, confidence, scoring, workflow engine
2. **All interactions are deterministic** -- same inputs → same outputs
3. **Evidence-first** -- every finding backed by statistical test with p-value or effect size
4. **Statistical validity before convenience** -- KS alpha=0.05, PSI threshold 0.25
5. **Test before code** -- write failing test first, then implement
6. **One module per concern** -- keep modules focused
7. **No secrets in code** -- use .env, never commit credentials
8. **Pre-commit hooks** -- must pass before commit

## Remediation Status (2026-07-23)

All 4 phases of the end-to-end remediation plan are **COMPLETE**:
- **Phase 1**: Critical stabilization (benchmark, extraction, scoring, security) — 7 files modified
- **Phase 2**: Reliability & observability (workspace detection, evidence schema, API hardening) — 5 files modified
- **Phase 3**: Polish & UX (CLI help text, optional dependencies, CORS/security headers) — 3 files modified
- **Phase 4**: Hardening & documentation (30 regression tests, docs updated) — 2 test files, 2 docs updated

**Scientific Remediation (2026-07-24)**: 6 audit findings resolved:
- **FIX-1**: Severity extraction fallback reads actual detector fields (`ks_statistic`, `delta_pearson`, `compression_index`) instead of non-existent `severity` key
- **FIX-2**: KS p-value uses `scipy.stats.ks_2samp` for n<30, custom asymptotic for n>=30
- **FIX-3**: D-01 and D-03 switched from Bonferroni to Holm-Bonferroni (uniformly more powerful)
- **FIX-4**: D-02 breakdown detection uses `max(|Pearson|, |Spearman|)` with sign from dominant correlation
- **FIX-5**: Effect sizes present in diagnostics; primary output uses actual detector fields
- **FIX-6**: Cliff's delta vectorized with numpy broadcasting (`x[:, None] > y[None, :]`)

## Documentation Hierarchy

1. `CLAUDE.md` -- This file (repository constitution)
2. `MEMORY.md` -- Agent working memory (current session context)
3. `README.md` -- User-facing documentation
4. `CHANGELOG.md` -- Version history
5. `docs/architecture.md` -- Architecture overview
6. `docs/getting_started.md` -- Quick start guide
7. `docs/configuration.md` -- Configuration reference
8. `docs/cli_reference.md` -- CLI commands reference
9. `docs/metrics.md` -- Metrics specification
10. `docs/metric_requirements.md` -- Detailed metric requirements
11. `docs/specifications/` -- Numbered scientific/engineering specs
12. `reports/` -- Generated analysis reports

## Current Status (2026-07-23)

- **All 7 metrics working**: M-01 through M-07 tested on 6 repos (Click, MarkupSafe, Jinja, Requests, Flask, Django)
- **No timeouts**: All analyses complete under 31s (Django 34K commits: 28.3s)
- **Scalability Phase 5 COMPLETE**: Numstat bottleneck fixed — `git log --numstat` hang on Windows resolved via file-based streaming with 5K commit limit
- **2775 tests passing**: 2 failed (pre-existing architecture), 6 skipped (+ 24 regression tests for remediation)
- **Remediation COMPLETE**: All 4 phases done — Phase 1 critical stabilization, Phase 2 reliability, Phase 3 polish, Phase 4 regression tests
- **Scientific Remediation COMPLETE**: All 6 audit findings fixed — severity extraction, KS p-value, Holm-Bonferroni, D-02 max correlation, effect sizes, vectorized Cliff's delta
- **GitHub auth**: dotenv auto-loading for M-05 extraction
- **Windows encoding**: cp1252 fixes applied to all subprocess tests
- **Doctor command**: `miie doctor` for system health checks
- **Metric sources**: Dashboard shows git/api/proxy indicators
- **D-03 fix**: None values filtered in adapter and metric extractor (not frozen core)
- **Confidence score**: Fixed — now 1.0/1.0 on Markupsafe (was 0.062)
- **Missing data factor**: Fixed — aggregate metrics (M-01/M-04/M-07) no longer count as missing in every window
- **End-to-end hardening**: Git timeout, disk cleanup, bare except cleanup, CLI knobs, network retry, token validation, API auth — ALL COMPLETE
- **War-room fixes**: Confidence band surfaced first, `--fail-on-low-confidence` flag, data quality section, evidence compression, monorepo hint — ALL COMPLETE
- **Unicode encoding fix**: `─` box-drawing character replaced with ASCII `-` in premium_tui.py and brand_header.py to prevent cp1252 crash
- **Platform**: Windows-only — no Linux/macOS CI, no cross-platform guarantees

## CI/CD

- **Pre-commit**: black, isort, flake8, mypy
- **Makefile**: `make lint`, `make typecheck`, `make test`
- **Tests**: pytest with coverage
- **Build**: poetry build
- **Docker**: Dockerfile + docker-compose.yml available
