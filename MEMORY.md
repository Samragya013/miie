# MEMORY.md -- Agent Working Memory

## Repository State

- **Version**: 1.6.1
- **Package**: `miie` (src layout: `src/miie/`)
- **Tests**: 2849 passing (pytest), 2 pre-existing failures (architecture), 6 skipped
- **Python**: 3.10-3.12
- **Platform**: **Windows-only** (no Linux/macOS CI, no cross-platform guarantees)
- **License**: MIT

## Current Status: Security Hardening COMPLETE

End-to-end security remediation complete. 20 red team findings (7 High, 9 Medium, 4 Low) identified. All P0/P1 fixes applied. Ship gate: 19 PASS, 0 CRITICAL, 0 HIGH. 29 regression tests written and passing.

## Recent Work

- **CI/CD Security Hardening (2026-07-25)**: Pipeline attack surface audit + fixes
  - ci.yml: Added `permissions: contents: read` (least privilege)
  - release.yml: Removed unused `id-token: write` permission
  - release.yml: Added `sha256sum` integrity verification for artifact downloads
  - All actions already SHA-pinned (from prior session)
  - No workflow injection, no pull_request_target, no self-hosted runners
  - 23 CI/CD regression tests added (`tests/regression/test_cicd_security.py`)
  - Audit script: `scripts/cicd_audit.py`
  - **Audit verdict**: 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW
  - `.dockerignore` created — blocks `.env`, `.git/`, `tests/`, `archive/` from Docker layers
  - `Dockerfile` hardened — non-root `miie` user, `HEALTHCHECK`, no `-e` pip flag
  - `docker-compose.yml` fixed — API bound to `127.0.0.1:8000`, `MIIE_API_KEY` env var
  - `requirements.txt` synced — upper bounds, `defusedxml` added
  - API rate limiting — 30 req/min with `threading.Lock` (atomic)
  - `JobStore` LRU eviction — 200 job cap prevents OOM
  - CORS `allow_headers` locked to `X-API-Key`, `Content-Type` only
  - CI/CD workflows pinned to full commit SHAs
  - `setup.cfg` updated — mypy Python 3.12, strict error codes
  - `git.py` token-in-URL fix — `GIT_ASKPASS` instead of embedding token
  - Workspace ID sanitization — recursive `..` stripping + `is_relative_to()`
  - `output_dir` validation — traversal + sensitive system dir blocklist
  - `SECURITY.md` updated — v1.6.x support, full security architecture docs
  - **P1 Git hook prevention**: `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0` added to all git subprocess calls in ingestion.py, commit_extractor.py, engine.py, generator.py
  - **29 regression tests** written and passing (`tests/regression/test_security_hardening.py`)
  - **Ship gate**: 19 PASS, 0 CRITICAL, 0 HIGH — CLEAR TO SHIP
  - **Commits pushed**: b02ab34 (hardening), 45418e0 (regression tests)
- **Monitoring Setup Guide**: `docs/monitoring_setup_guide.md` — four golden signals, structured logging schema, alert rules
- **TUI UX Enhancement**: In-process analysis, unified nav, help overlay, history, skippable splash
- **Design Critique**: 8 TUI issues identified across Nielsen's heuristics, Gestalt, JTBD
- **Scientific Remediation**: 6 audit findings resolved (severity extraction, KS p-value, Holm-Bonferroni, D-02 max correlation, effect sizes, vectorized Cliff's delta)
- **Root directory cleanup**: 14 spec files deleted, red_team files moved to archive/, threats_cli.json moved to schemas/
- **Tests expanded**: 2758 → 2826 (29 security regression + 32 earlier + 7 earlier)
- **Tags pushed**: v1.6.0 and v1.6.1

## Frozen Core (DO NOT MODIFY)

- Metrics: M-01 through M-07 (`src/miie/metrics/`)
- Detectors: D-01, D-02, D-03 (`src/miie/processing/detection/`)
- Evidence: EvidencePackage (`src/miie/processing/evidence.py`)
- Confidence/Integrity: `src/miie/schemas/models.py`
- Statistics: `src/miie/processing/detection/statistics.py`
- WorkflowEngine: `src/miie/application/workflow.py`
- SessionManager: `src/miie/application/session.py`
- ApplicationService: `src/miie/application/service.py`
- All contracts: `src/miie/contracts/interfaces.py`

## Repository Structure

```
src/miie/
├── api/                    # FastAPI REST (6 frozen endpoints)
├── application/            # Interactive layer, workflow, session
├── benchmark/              # Benchmark execution engine
├── cli/                    # Click CLI (16 commands + TUI)
├── config/                 # Configuration loader
├── contracts/              # Interfaces (frozen)
├── experimental/           # Non-production code
├── metrics/                # M-01 through M-07
├── observation_graph/      # Observation graph data structures
├── orchestration/          # Workflow orchestration
├── processing/             # Core scientific processing
│   ├── detection/          # D-01, D-02, D-03 + statistics
│   ├── evidence.py         # EvidencePackage
│   ├── evaluation/         # Evaluation engine
│   ├── explanation/        # Explanation engine
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
├── utils/                  # Utilities
├── validation/             # Validation framework
└── workspace/              # Persistent workspace (ECP-03)
```

## Key Commands

- `pytest` -- Run all tests
- `black --line-length 120 .` -- Format
- `isort --profile black .` -- Sort imports
- `flake8 .` -- Lint
- `mypy src/miie/` -- Type check
- `make lint` -- Run all linters
- `make test` -- Run tests with coverage

## Directory Purposes

| Directory | Purpose |
|-----------|---------|
| `docs/` | 200+ documentation files (specs, guides, API docs) |
| `docs/specifications/` | Numbered scientific/engineering specifications |
| `tests/` | Test suite (2826 tests) |
| `tests/architecture/` | Layer dependency, package structure tests |
| `tests/regression/` | Security hardening regression tests (29 tests) |
| `benchmarks/` | Benchmark results + cloned repos |
| `reports/` | Generated analysis reports (FFP-01 through SXP-01) |
| `archive/` | Historical code and outputs |
| `schemas/` | YAML/JSON schema definitions |
| `scripts/` | Development scripts (gitignored) |

## Program History

| # | Program | Status | Tests | Reports | Verdict |
|---|---------|--------|-------|---------|---------|
| 1 | RSP-01 | Complete | — | 10 | Stabilized |
| 2 | RSP-02 | Complete | 2733 | 10 | Healthy |
| 3 | FFP-01 | Complete | 2705 | 11 | FROZEN |
| 4 | SCCP-01 | Complete | 2707 | 10 | COMPLETE |
| 5 | SCCP-02 | Complete | 2733 | 10 | COMPLETE |
| 6 | RRP-01 | Complete | 2733 | 10 | RELEASE READY |
| 7 | IVP-01 | Complete | 2733 | 10 | CONDITIONALLY CERTIFIED |
| 8 | RPP-01 | Complete | 2733 | 10 | ARTIFACT COMPLETE |
| 9 | PGP-01 | Complete | 2733 | 10 | PLATFORM GOVERNANCE COMPLETE |
| 10 | OIAP-01 | Complete | 2733 | 14 | NO (audit-only) |
| 11 | SXP-01 | Complete | 2735 | 14 | CONDITIONALLY CERTIFIED |

**Total Programs**: 11 complete
**Total Reports**: 129
**Current Tests**: 2849 passing

## Development Rules

1. No modifications to frozen core
2. All interactions are deterministic
3. Evidence-first: every finding backed by statistical test
4. Statistical validity before convenience
5. Test before code
6. One module per concern
7. No secrets in code
8. Pre-commit hooks must pass
