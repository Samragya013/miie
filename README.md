# MIIE — Measurement Integrity Intelligence Engine

[![CI](https://github.com/Samragya013/miie/actions/workflows/ci.yml/badge.svg)](https://github.com/Samragya013/miie/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.6.0-orange.svg)](https://github.com/Samragya013/miie/releases/tag/v1.6.0)

A research tool for evaluating whether software engineering metrics remain trustworthy representations of the constructs they claim to measure.

---

## Quick Start

```bash
# Install
pip install miie

# Analyze a local repository
miie analyze /path/to/repo

# Analyze a GitHub repository
miie analyze https://github.com/user/repo --auth-token YOUR_TOKEN

# Show version
miie --version
```

---

## Overview

MIIE analyzes git repositories to detect anomalies in development patterns using statistical methods. It identifies distribution drift, correlation breakdown, and threshold compression in commit frequency metrics.

### Mission

To provide a reproducible, open-source tool for metric validation in software engineering research.

### Scope

- CLI-first
- Offline-first
- Deterministic
- Benchmark-driven
- Research-oriented

### Non-Goals

- Not a SaaS platform
- Not a dashboard
- Not a web platform
- Not an enterprise analytics suite
- Not a developer productivity system
- Not an employee ranking platform

---

## Installation

### From PyPI (Recommended)

```bash
pip install miie
```

### From Source

```bash
git clone https://github.com/Samragya013/miie.git
cd miie
pip install .
```

### Development Setup

```bash
git clone https://github.com/Samragya013/miie.git
cd miie
pip install -e ".[dev]"
# Or with Poetry:
poetry install
poetry run pre-commit install
```

### Docker

```bash
# Build and run
docker compose run miie --version

# Analyze a repository
docker compose run miie analyze /path/to/repo
```

### Verify Installation

```bash
miie --version
# or
python -m miie --version
```

---

## CLI Reference

### Commands

| Command | Description |
|---|---|
| `analyze` | Full pipeline analysis |
| `ingest` | Ingest commits from repository |
| `detect` | Run anomaly detection |
| `explain` | Generate explanations |
| `export` | Export results in specified formats |
| `evaluate` | Evaluate benchmark results |
| `generate` | Generate synthetic benchmark candidates |
| `benchmark` | Execute benchmark suite |
| `validate` | Validate config or output |
| `status` | Show project status |
| `setup` | Interactive configuration wizard |

### Global Options

| Option | Description |
|---|---|
| `--version` | Show version and exit |
| `-c, --config PATH` | Path to config file |
| `-o, --output PATH` | Output directory |
| `-V, --verbose` | Enable verbose output |
| `--debug` | Enable debug mode |

### Analyze Options

| Option | Description |
|---|---|
| `--dry-run` | Show what would be analyzed |
| `--metrics M-01,M-02` | Specific metrics to compute |
| `--detectors D-01,D-02` | Specific detectors to run |
| `--window-size N` | Time window size in days |
| `--format json` | Output format |
| `--export-markdown` | Export as Markdown report |
| `--export-json` | Export as JSON report |
| `--export-csv` | Export as CSV report |
| `--export-html` | Export as HTML report |
| `--auth-token TOKEN` | GitHub authentication token |

### Examples

```bash
# Analyze a local repository
miie analyze /path/to/repo

# Analyze with specific metrics
miie analyze /path/to/repo --metrics M-01,M-02,M-06

# Analyze with specific detectors
miie analyze /path/to/repo --detectors D-01,D-02

# Dry run to see what would be analyzed
miie analyze /path/to/repo --dry-run

# Export as Markdown
miie analyze /path/to/repo --export-markdown

# Export as JSON
miie analyze /path/to/repo --export-json

# Verbose output with timing
miie analyze /path/to/repo --verbose

# Analyze GitHub repo with auth token
miie analyze https://github.com/user/repo --auth-token ghp_xxxxx

# Interactive CLI mode
python -m miie  # or just `miie`
```

### Example Output

```
$ miie analyze flask --verbose

Stage 1/9: Ingesting commits... OK (2.3s)
Stage 2/9: Extracting metrics... OK (5.1s)
Stage 3/9: Segmenting time-series... OK (0.2s)
Stage 4/9: Detecting anomalies... OK (1.8s)
Stage 5/9: Computing scores... OK (0.3s)
Stage 6/9: Packaging evidence... OK (0.1s)
Stage 7/9: Sampling... OK (0.1s)
Stage 8/9: Observing... OK (0.1s)
Stage 9/9: Building report... OK (0.2s)

Analysis Complete
Repository: flask
Integrity: 1.000 (Very High)
Confidence: 0.993 (Very High)
Risk: Very Low

Detectors:
  D-01 (Distribution Drift): PASS
  D-02 (Correlation Breakdown): PASS
  D-03 (Threshold Compression): PASS
```

---

## Python API

```python
from miie.orchestration.pipeline import AnalysisPipeline
from miie.config.loader import load_config

# Load configuration
config = load_config()

# Run pipeline
pipeline = AnalysisPipeline(config)
results = pipeline.run("/path/to/repo")

# Access results
print(f"Integrity: {results['integrity_score']}")
print(f"Confidence: {results['confidence_score']}")
```

See [docs/API_GUIDE.md](docs/API_GUIDE.md) for full API reference.

---

## Architecture

```
CLI (10 commands)
    |
Pipeline (9 stages)
    |
Detectors (3 anomaly types)
    |
Output (JSON, Markdown, CSV, HTML, forensic evidence)
```

### Pipeline Stages

1. **Ingestion** — Clone and parse git history
2. **Extraction** — Compute metric values
3. **Segmentation** — Split into time windows
4. **Detection** — Run anomaly detectors
5. **Scoring** — Compute integrity/confidence scores
6. **Evidence** — Package forensic evidence
7. **Sampling** — Apply sampling strategies
8. **Observation** — Observation framework
9. **Reporting** — Generate output

### Detectors

| ID | Name | Statistical Method |
|---|---|---|
| D-01 | Distribution Drift | Kolmogorov-Smirnov, PSI |
| D-02 | Correlation Breakdown | Pearson r, Spearman ρ, Fisher-z |
| D-03 | Threshold Compression | Excess Mass, Hartigan's Dip |

### Metrics

| ID | Name | Description |
|---|---|---|
| M-01 | Commit Frequency | Commits per time window |
| M-02 | Code Churn | Lines added/removed per window |
| M-06 | Author Count | Unique authors per window |

---

## Configuration

MIIE uses a YAML/JSON configuration file. Default locations:

- `~/.miie/config.json` (user-level)
- `.miie/config.json` (project-level)

```bash
# Interactive setup wizard
miie setup

# Show current config
miie status

# Use custom config
miie analyze /path/to/repo -c /path/to/config.yaml
```

---

## Documentation

| Document | Description |
|---|---|
| [Quick Start](#quick-start) | Get running in 2 minutes |
| [CLI Guide](docs/CLI_GUIDE.md) | Complete CLI reference |
| [API Guide](docs/API_GUIDE.md) | Python API reference |
| [Installation](docs/INSTALLATION.md) | Platform-specific install |
| [Examples](examples/) | Runnable example gallery |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and fixes |
| [Contributing](CONTRIBUTING.md) | Development workflow |
| [Changelog](CHANGELOG.md) | Version history |
| [Release Notes](docs/release/RELEASE_NOTES_v1.6.md) | v1.6.0 release notes |

---

## Limitations

| Limitation | Workaround |
|---|---|
| Repos with >100K commits may timeout | Increase timeout or reduce window |
| Windows terminal Unicode issues | Use Windows Terminal or WSL |
| Minimum sample size gates | Use repos with sufficient history |

---

## Roadmap

### v1.7 (Planned)

- Configurable timeout for large repositories
- Cross-platform CI testing
- Additional anomaly detectors
- REST API endpoints

### v2.0 (Future)

- Observation Engine enhancements
- Real-time monitoring
- Multi-repository batch analysis
- Custom detector plugins

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding conventions, and pull request workflow.

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

---

## Support

- **Documentation**: `docs/` directory
- **Architecture**: `docs/architecture/`
- **Release Notes**: `docs/release/`
- **Issues**: [GitHub Issues](https://github.com/Samragya013/miie/issues)
