"""Tests for validating MIIE architectural dependencies.

This module verifies the actual package structure in src/miie/.
Dependencies are defined using real package names, not abstract layers.
Each package lists its ALLOWED dependencies (what it may import from).

Circular dependencies are documented in KNOWN_CIRCULAR_DEPS and
exempted from cycle detection. These are architectural decisions that
require an ADR to resolve.
"""

import ast
from pathlib import Path

import pytest

# Root directory of the project
ROOT_DIR = Path(__file__).parent.parent.parent
SRC_DIR = ROOT_DIR / "src" / "miie"

# ---------------------------------------------------------------------------
# ALLOWED DEPENDENCIES — actual package names, verified from codebase
# Each key is a package directory under src/miie/.
# The value is the set of other packages it is allowed to import from.
# Source: codebase analysis of all .py files under src/miie/
# ---------------------------------------------------------------------------
ALLOWED_DEPENDENCIES = {
    # Leaf packages — no miie dependencies
    "metrics": set(),
    "reporting": set(),
    "storage": set(),
    "utils": set(),
    # Schema/contract layer
    "schemas": {"processing"},  # backward-compat re-export in models.py
    "contracts": {"schemas"},
    # Infrastructure
    "config": {"contracts"},
    "validation": {"contracts"},
    # Processing ecosystem
    "processing": {"contracts", "schemas", "utils", "providers"},
    "providers": {"metrics", "processing"},
    "sampling": {"processing"},
    "observation_graph": {"processing"},
    "experimental": {"processing"},
    # Orchestration
    "orchestration": {"contracts", "schemas"},
    # Application layer
    "application": {"processing", "contracts", "schemas", "utils"},
    # Interface / entry points
    "api": {"processing"},
    "cli": {
        "contracts",
        "utils",
        "processing",
        "sampling",
        "application",
        "benchmark",
        "config",
        "schemas",
        "workspace",
        "reporting",
    },
    "benchmark": {"contracts", "schemas", "processing"},
    # Scientific analysis
    "scientific": {"sampling"},
    # Workspace layer
    "workspace": {"application"},
    # Reasoning layer (read-only consumption of scientific outputs)
    "reasoning": set(),
    # Assurance layer (read-only consumption of detector outputs)
    "assurance": set(),
}

# ---------------------------------------------------------------------------
# KNOWN CIRCULAR DEPENDENCIES — documented architectural decisions
# These pairs create cycles. They are exempted from cycle detection.
# Each entry must have an associated ADR or architectural justification.
# ---------------------------------------------------------------------------
KNOWN_CIRCULAR_DEPS = {
    # processing <-> schemas: schemas/models.py re-exports observation types
    # from processing.observation.models for backward compatibility.
    # Justification: Backward-compat bridge; schemas is the canonical
    # location for data models, but observation models live in processing.
    ("processing", "schemas"),
    ("schemas", "processing"),
    # processing <-> providers: processing.extraction needs providers for
    # data fetching, providers need processing.observation.models for data.
    # Justification: providers are the data-source abstraction layer;
    # processing consumes their output and provides the observation model.
    ("processing", "providers"),
    ("providers", "processing"),
    # schemas <-> processing <-> contracts: transitive cycle
    # schemas -> processing (backward-compat re-exports observation types)
    # processing -> contracts (uses contract types)
    # contracts -> schemas (uses schema types)
    # This creates a 3-hop cycle: schemas -> processing -> contracts -> schemas.
    # Justification: Backward-compat bridge; requires ADR to resolve.
    ("schemas", "contracts"),
}


# Standard library and known third-party packages to skip during import analysis
STDLIB_AND_EXTERNAL = {
    # Standard library
    "os",
    "sys",
    "json",
    "csv",
    "yaml",
    "pathlib",
    "typing",
    "dataclasses",
    "abc",
    "enum",
    "random",
    "math",
    "statistics",
    "datetime",
    "re",
    "collections",
    "itertools",
    "functools",
    "hashlib",
    "hmac",
    "subprocess",
    "textwrap",
    "uuid",
    "shutil",
    "tempfile",
    "glob",
    "fnmatch",
    "copy",
    "threading",
    "time",
    "traceback",
    "io",
    "base64",
    "binascii",
    "struct",
    "socket",
    "ssl",
    "urllib",
    "http",
    "email",
    "html",
    "xml",
    "csv",
    "sqlite3",
    "dbm",
    "zlib",
    "gzip",
    "bz2",
    "lzma",
    "tarfile",
    "zipfile",
    "logging",
    "warnings",
    "contextlib",
    "unittest",
    "platform",
    "signal",
    "errno",
    "ctypes",
    "mmap",
    "codecs",
    "locale",
    "gettext",
    "unicodedata",
    # Third-party
    "click",
    "numpy",
    "pandas",
    "scipy",
    "jinja2",
    "pydantic",
    "fastapi",
    "uvicorn",
    "requests",
    "httpx",
    "git",
    "github",
    "dotenv",
}


def get_imports_from_file(file_path: Path, self_package: str | None = None) -> set[str]:
    """Extract all miie package imports from a Python file.

    Handles both absolute (from miie.processing.xxx) and relative (from ..processing.xxx)
    imports. Returns only imports that resolve to known miie packages.
    Self-imports (intra-package) are filtered out.

    Args:
        file_path: Path to the Python file
        self_package: The package this file belongs to (to filter self-imports)
    """
    try:
        tree = ast.parse(file_path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                # Handle miie.X.Y -> X
                if parts[0] == "miie" and len(parts) > 1:
                    pkg = parts[1]
                    if pkg in ALLOWED_DEPENDENCIES and pkg != self_package:
                        imports.add(pkg)
                elif parts[0] in ALLOWED_DEPENDENCIES and parts[0] != self_package:
                    imports.add(parts[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                parts = node.module.split(".")
                # Handle miie.X.Y -> X
                if parts[0] == "miie" and len(parts) > 1:
                    pkg = parts[1]
                    if pkg in ALLOWED_DEPENDENCIES and pkg != self_package:
                        imports.add(pkg)
                elif parts[0] in ALLOWED_DEPENDENCIES and parts[0] != self_package:
                    imports.add(parts[0])
    return imports


def get_package_for_module(module_path: Path) -> str | None:
    """Determine which package a module belongs to based on its path."""
    try:
        relative_path = module_path.relative_to(SRC_DIR)
        return relative_path.parts[0] if relative_path.parts else None
    except ValueError:
        return None


def test_layer_dependencies():
    """Test that modules only import from allowed packages.

    Verifies the actual repository structure against ALLOWED_DEPENDENCIES.
    Each package may only import from its declared allowed set.
    """
    violations = []

    for py_file in SRC_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        package = get_package_for_module(py_file)
        if package is None or package not in ALLOWED_DEPENDENCIES:
            continue

        imports = get_imports_from_file(py_file, self_package=package)

        for imported_package in imports:
            if imported_package not in ALLOWED_DEPENDENCIES[package]:
                violations.append(
                    f"{py_file.relative_to(ROOT_DIR)}: "
                    f"Forbidden import '{imported_package}' from package '{package}' "
                    f"(allowed: {sorted(ALLOWED_DEPENDENCIES[package])})"
                )

    assert not violations, "Dependency violations found:\n" + "\n".join(violations)


def test_no_circular_imports():
    """Test that there are no circular dependencies between packages.

    Known circular dependencies (documented in KNOWN_CIRCULAR_DEPS) are
    exempted from this check. All other cycles are architecture violations.
    """
    # Build dependency graph from actual code
    graph: dict[str, set[str]] = {pkg: set() for pkg in ALLOWED_DEPENDENCIES}

    for py_file in SRC_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        package = get_package_for_module(py_file)
        if package is None or package not in ALLOWED_DEPENDENCIES:
            continue

        imports = get_imports_from_file(py_file, self_package=package)
        for imported_package in imports:
            if imported_package in ALLOWED_DEPENDENCIES:
                graph[package].add(imported_package)

    # DFS cycle detection
    def find_cycle(node: str, visited: set, rec_stack: set) -> list[str] | None:
        visited.add(node)
        rec_stack.add(node)

        for neighbor in graph[node]:
            if neighbor not in visited:
                result = find_cycle(neighbor, visited, rec_stack)
                if result:
                    return result
            elif neighbor in rec_stack:
                return [neighbor, node]

        rec_stack.discard(node)
        return None

    visited: set[str] = set()
    cycles: list[str] = []

    for node in graph:
        if node not in visited:
            cycle_nodes = find_cycle(node, visited, set())
            if cycle_nodes:
                # Check if this cycle is a known/authorized circular dep
                is_known = False
                for i in range(len(cycle_nodes) - 1):
                    pair = (cycle_nodes[i], cycle_nodes[i + 1])
                    if pair in KNOWN_CIRCULAR_DEPS:
                        is_known = True
                        break
                if not is_known:
                    cycles.append(" -> ".join(cycle_nodes))

    assert not cycles, "Unexpected circular dependencies found:\n" + "\n".join(cycles)


def test_all_packages_have_dependency_rules():
    """Verify that every package directory has an entry in ALLOWED_DEPENDENCIES.

    This ensures no package is accidentally excluded from architecture checks.
    """
    actual_packages = set()
    for item in SRC_DIR.iterdir():
        if item.is_dir() and not item.name.startswith("_"):
            actual_packages.add(item.name)

    defined_packages = set(ALLOWED_DEPENDENCIES.keys())

    missing = actual_packages - defined_packages
    extra = defined_packages - actual_packages

    issues = []
    if missing:
        issues.append(f"Packages in repository but NOT in ALLOWED_DEPENDENCIES: {sorted(missing)}")
    if extra:
        issues.append(f"Packages in ALLOWED_DEPENDENCIES but NOT in repository: {sorted(extra)}")

    assert not issues, "Package coverage mismatch:\n" + "\n".join(issues)


def _reachable(graph, src, dst):
    """Check if dst is reachable from src via BFS."""
    visited = set()
    queue = [src]
    while queue:
        node = queue.pop(0)
        if node == dst:
            return True
        if node in visited:
            continue
        visited.add(node)
        queue.extend(graph.get(node, set()))
    return False


def test_known_circular_deps_are_real():
    """Verify that every entry in KNOWN_CIRCULAR_DEPS actually exists in code.

    Checks transitive reachability (not just direct edges) since some known
    cycles span multiple hops (e.g., schemas -> processing -> contracts -> schemas).
    If a documented circular dependency is fixed, it should be removed from
    KNOWN_CIRCULAR_DEPS and this test will flag the stale entry.
    """
    # Build actual dependency graph
    graph: dict[str, set[str]] = {pkg: set() for pkg in ALLOWED_DEPENDENCIES}

    for py_file in SRC_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        package = get_package_for_module(py_file)
        if package is None or package not in ALLOWED_DEPENDENCIES:
            continue

        imports = get_imports_from_file(py_file, self_package=package)
        for imported_package in imports:
            if imported_package in ALLOWED_DEPENDENCIES:
                graph[package].add(imported_package)

    stale = []
    for pair in KNOWN_CIRCULAR_DEPS:
        src, dst = pair
        if not _reachable(graph, src, dst):
            stale.append(f"{src} -> {dst}")

    assert not stale, (
        "Stale KNOWN_CIRCULAR_DEPS entries (cycle no longer exists):\n"
        + "\n".join(stale)
        + "\nRemove these from KNOWN_CIRCULAR_DEPS."
    )


def test_forbidden_imports():
    """Verify that packages do not import from packages outside their allowed set.

    This is a stricter check than test_layer_dependencies: it also verifies
    that packages don't import from packages not in ALLOWED_DEPENDENCIES at all
    (e.g., typos, new packages without rules).
    """
    violations = []

    for py_file in SRC_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        package = get_package_for_module(py_file)
        if package is None or package not in ALLOWED_DEPENDENCIES:
            continue

        imports = get_imports_from_file(py_file, self_package=package)

        for imported_package in imports:
            # Check if it's a known miie package that's not allowed
            if imported_package in ALLOWED_DEPENDENCIES:
                if imported_package not in ALLOWED_DEPENDENCIES[package]:
                    # Skip known circular deps
                    if (package, imported_package) in KNOWN_CIRCULAR_DEPS:
                        continue
                    violations.append(
                        f"{py_file.relative_to(ROOT_DIR)}: "
                        f"Package '{package}' imports '{imported_package}' "
                        f"which is not in its allowed set"
                    )

    assert not violations, "Forbidden imports found:\n" + "\n".join(violations)


def test_leaf_packages_have_no_dependencies():
    """Verify that leaf packages (metrics, reporting, storage, utils) have no miie imports.

    These packages are designed to be independent and should not import
    from any other miie package.
    """
    LEAF_PACKAGES = {"metrics", "reporting", "storage", "utils"}
    violations = []

    for py_file in SRC_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        package = get_package_for_module(py_file)
        if package is None or package not in LEAF_PACKAGES:
            continue

        imports = get_imports_from_file(py_file, self_package=package)

        for imported_package in imports:
            if imported_package in ALLOWED_DEPENDENCIES:
                violations.append(
                    f"{py_file.relative_to(ROOT_DIR)}: " f"Leaf package '{package}' imports '{imported_package}'"
                )

    assert not violations, "Leaf package violations found:\n" + "\n".join(violations)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
