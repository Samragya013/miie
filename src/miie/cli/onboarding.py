"""Onboarding wizard for MIIE first-run experience.

Provides a guided setup experience for new users, including
system checks, configuration, and first analysis walkthrough.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from rich.prompt import Confirm, Prompt
from rich.table import Table

from .display import (
    console,
    info_panel,
    print_divider,
    print_kv_aligned,
    print_section,
    success_panel,
)
from .interactive import (
    CONFIG_DIR,
    CONFIG_FILE,
    ensure_config_dir,
    load_config,
    save_config,
)

# ── Version Check ──────────────────────────────────────────────────────
ONBOARDING_VERSION = "1.0"
ONBOARDING_MARKER = CONFIG_DIR / ".onboarded"


def is_first_run() -> bool:
    """Check if this is the first time running MIIE."""
    return not ONBOARDING_MARKER.exists()


def mark_onboarded() -> None:
    """Mark onboarding as complete."""
    ensure_config_dir()
    ONBOARDING_MARKER.write_text(
        json.dumps({"version": ONBOARDING_VERSION, "completed": True}),
        encoding="utf-8",
    )


# ── System Checks ──────────────────────────────────────────────────────
def run_system_checks() -> dict[str, bool]:
    """Run system prerequisite checks."""
    print_section("System Checks")

    checks = {}

    # Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    checks["Python 3.10+"] = py_ok
    status = "[green]OK[/green]" if py_ok else "[red]FAIL[/red]"
    console.print(f"  Python {py_version}: {status}")

    # Git
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        git_ok = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        git_ok = False
    checks["Git"] = git_ok
    status = "[green]OK[/green]" if git_ok else "[red]FAIL[/red]"
    console.print(f"  Git: {status}")

    # MIIE package
    try:
        import miie

        miie_ok = True
    except ImportError:
        miie_ok = False
    checks["MIIE package"] = miie_ok
    status = "[green]OK[/green]" if miie_ok else "[red]FAIL[/red]"
    console.print(f"  MIIE package: {status}")

    # Config directory
    config_ok = CONFIG_DIR.exists() or CONFIG_DIR.parent.exists()
    checks["Config directory"] = config_ok
    status = "[green]OK[/green]" if config_ok else "[yellow]Will create[/yellow]"
    console.print(f"  Config directory: {status}")

    console.print()
    return checks


# ── Configuration Setup ────────────────────────────────────────────────
def setup_configuration() -> dict:
    """Interactive configuration setup."""
    config = load_config()

    print_section("Configuration")

    # GitHub Token
    console.print("  [dim]A GitHub token is required for analyzing private repositories.[/dim]")
    console.print("  [dim]Public repositories work without a token.[/dim]")
    console.print()

    current_token = config.get("github_token", os.environ.get("GITHUB_TOKEN", ""))
    if current_token:
        masked = current_token[:4] + "..." + current_token[-4:] if len(current_token) > 8 else "****"
        console.print(f"  Current token: {masked}")
        if not Confirm.ask("  [cyan]Keep current token?[/cyan]", default=True):
            config["github_token"] = Prompt.ask("  [bold cyan]GitHub token[/bold cyan]", password=True)
    else:
        if Confirm.ask("  [cyan]Configure GitHub token now?[/cyan]", default=False):
            config["github_token"] = Prompt.ask("  [bold cyan]GitHub token[/bold cyan]", password=True)

    # Output directory
    console.print()
    config["output_dir"] = Prompt.ask(
        "  [bold cyan]Default output directory[/bold cyan]",
        default=config.get("output_dir", "./output"),
    )

    # Parallelism
    console.print()
    config["parallelism"] = int(
        Prompt.ask(
            "  [bold cyan]Parallel analysis threads[/bold cyan]",
            default=str(config.get("parallelism", 1)),
        )
    )

    # Theme
    console.print()
    config["theme"] = Prompt.ask(
        "  [bold cyan]Color theme[/bold cyan]",
        choices=["auto", "dark", "light"],
        default=config.get("theme", "auto"),
    )

    save_config(config)
    console.print()
    console.print("  [green]Configuration saved![/green]")
    console.print()

    return config


# ── First Analysis Walkthrough ─────────────────────────────────────────
def run_first_analysis_walkthrough() -> None:
    """Guide user through their first analysis."""
    print_section("First Analysis")

    console.print("  [dim]Let's run your first analysis![/dim]")
    console.print()

    # Ask for repository
    repo_path = Prompt.ask(
        "  [bold cyan]Repository path[/bold cyan]",
        default=".",
    )

    console.print()
    console.print(f"  [bold cyan]>>[/bold cyan] Analyzing [bold]{repo_path}[/bold]")
    console.print()

    # Run analysis
    try:
        result = subprocess.run(
            ["python", "-m", "miie", "analyze", repo_path, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            success_panel(
                "Analysis Complete",
                "Your first analysis has finished successfully!\n" "  Check the output directory for results.",
            )
        else:
            console.print(f"  [yellow]Analysis completed with warnings.[/yellow]")
            console.print(f"  [dim]{result.stderr[:200]}[/dim]")

    except subprocess.TimeoutExpired:
        console.print("  [yellow]Analysis timed out. Try a smaller repository.[/yellow]")
    except Exception as e:
        console.print(f"  [red]Error: {e}[/red]")

    console.print()


# ── Main Onboarding Flow ───────────────────────────────────────────────
def run_onboarding() -> bool:
    """Run the full onboarding wizard.

    Returns:
        True if onboarding completed, False if skipped.
    """
    if not is_first_run():
        return False

    console.print()
    info_panel(
        "Welcome to MIIE!",
        "Measurement Integrity Intelligence Engine v1.6.0\n" "Let's get you set up in just a few steps.",
    )
    console.print()

    # Step 1: System checks
    checks = run_system_checks()

    if not all(checks.values()):
        console.print("  [yellow]Some checks failed. You may need to install dependencies.[/yellow]")
        console.print("  [dim]Run: pip install miie[/dim]")
        console.print()

        if not Confirm.ask("  [cyan]Continue anyway?[/cyan]", default=True):
            return False

    # Step 2: Configuration
    if Confirm.ask("  [cyan]Would you like to configure MIIE now?[/cyan]", default=True):
        setup_configuration()

    # Step 3: First analysis
    if Confirm.ask("  [cyan]Run a quick analysis to verify everything works?[/cyan]", default=True):
        run_first_analysis_walkthrough()

    # Mark complete
    mark_onboarded()

    success_panel(
        "Setup Complete",
        "MIIE is ready to use!\n\n"
        "  Quick start:\n"
        "    miie analyze /path/to/repo\n"
        "    miie shell /path/to/repo\n"
        "    miie interactive\n\n"
        "  Type 'miie --help' for all commands.",
    )

    return True
