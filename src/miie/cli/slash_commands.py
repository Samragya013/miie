"""Slash command system for MIIE interactive mode.

Provides Claude Code-style slash commands for interactive analysis.
Commands: /help, /analyze, /status, /export, /config, /history, /quit
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from rich.table import Table

from .display import (
    console,
    info_panel,
    print_divider,
    print_kv_aligned,
    print_section,
)

# ── Command Registry ───────────────────────────────────────────────────
COMMANDS: dict[str, dict[str, Any]] = {}


def command(name: str, description: str, usage: str = ""):
    """Decorator to register a slash command."""

    def decorator(func):
        COMMANDS[name] = {
            "handler": func,
            "description": description,
            "usage": usage,
        }
        return func

    return decorator


# ── Built-in Commands ──────────────────────────────────────────────────
@command("/help", "Show available commands", "/help [command]")
def cmd_help(args: list[str], context: dict) -> bool:
    """Display help for all commands or a specific command."""
    if args:
        raw = args[0].strip("/")
        cmd_name = f"/{raw}" if not raw.startswith("/") else raw
        if cmd_name in COMMANDS:
            info = COMMANDS[cmd_name]
            console.print(f"\n  [bold cyan]/{cmd_name}[/bold cyan]")
            console.print(f"  [dim]{info['description']}[/dim]")
            if info["usage"]:
                console.print(f"  [dim]Usage: {info['usage']}[/dim]")
            console.print()
        else:
            console.print(f"  [red]Unknown command: /{cmd_name}[/red]")
        return True

    table = Table(
        title="Available Commands",
        show_header=True,
        header_style="bold cyan",
        padding=(0, 2),
    )
    table.add_column("Command", style="bold white", width=16)
    table.add_column("Description", style="dim")
    table.add_column("Usage", style="dim")

    for name, info in sorted(COMMANDS.items()):
        table.add_row(name, info["description"], info["usage"])

    console.print()
    console.print(table)
    console.print()
    return True


@command("/status", "Show current analysis status", "/status")
def cmd_status(args: list[str], context: dict) -> bool:
    """Display current analysis status and context."""
    print_section("Current Status")

    if context.get("repo_path"):
        print_kv_aligned("Repository", context["repo_path"])
    else:
        print_kv_aligned("Repository", "[dim]Not set[/dim]")

    if context.get("last_result"):
        result = context["last_result"]
        print_kv_aligned("Last Analysis", result.get("timestamp", "unknown"))
        print_kv_aligned("Integrity Score", f"{result.get('integrity_score', 0):.3f}")
        print_kv_aligned("Confidence", f"{result.get('confidence', 0):.3f}")
    else:
        print_kv_aligned("Last Analysis", "[dim]None[/dim]")

    if context.get("output_dir"):
        print_kv_aligned("Output Dir", context["output_dir"])

    console.print()
    return True


@command("/analyze", "Run analysis on a repository", "/analyze [path]")
def cmd_analyze(args: list[str], context: dict) -> bool:
    """Run analysis on a repository."""
    repo_path = args[0] if args else context.get("repo_path", ".")

    console.print(f"\n  [bold cyan]>>[/bold cyan] [bold white]Starting Analysis[/bold white]")
    print_divider()
    print_kv_aligned("Repository", repo_path)
    print_kv_aligned("Mode", "Full pipeline")
    console.print()

    # Store for later use
    context["repo_path"] = repo_path
    context["analyze_requested"] = True

    return True


@command("/export", "Export results to file", "/export [format]")
def cmd_export(args: list[str], context: dict) -> bool:
    """Export analysis results."""
    fmt = args[0] if args else "json"

    if not context.get("last_result"):
        console.print("  [yellow]No results to export. Run /analyze first.[/yellow]")
        return True

    output_dir = context.get("output_dir", "./output")
    console.print(f"\n  [bold cyan]>>[/bold cyan] [bold white]Exporting Results[/bold white]")
    print_divider()
    print_kv_aligned("Format", fmt)
    print_kv_aligned("Output Dir", output_dir)
    console.print()

    context["export_requested"] = True
    context["export_format"] = fmt

    return True


@command("/config", "View or edit configuration", "/config [key] [value]")
def cmd_config(args: list[str], context: dict) -> bool:
    """View or modify configuration."""
    from .interactive import CONFIG_FILE, load_config, save_config

    config = load_config()

    if not args:
        # Show all config
        print_section("Configuration")
        for key, value in sorted(config.items()):
            if key == "github_token":
                val_str = str(value)
                masked = val_str[:4] + "..." + val_str[-4:] if len(val_str) > 8 else "****"
                print_kv_aligned(key, masked)
            else:
                print_kv_aligned(key, str(value))
        console.print()
        return True

    if len(args) == 1:
        # Show specific key
        key = args[0]
        value = config.get(key)
        if value is not None:
            print_kv_aligned(key, str(value))
        else:
            console.print(f"  [dim]Key '{key}' not found.[/dim]")
        return True

    # Set key=value
    key = args[0]
    value_str = " ".join(args[1:])

    # Type coercion
    if value_str.lower() in ("true", "false"):
        value = value_str.lower() == "true"
    elif value_str.isdigit():
        value = int(value_str)
    else:
        try:
            value = float(value_str)
        except ValueError:
            value = value_str

    config[key] = value
    save_config(config)
    console.print(f"  [green]Set {key} = {value}[/green]")
    return True


@command("/history", "Show recent analyses", "/history")
def cmd_history(args: list[str], context: dict) -> bool:
    """Show recent analysis history."""
    from .interactive import load_recent

    recent = load_recent()
    if not recent:
        console.print("  [dim]No recent analyses found.[/dim]")
        return True

    table = Table(
        title="Recent Analyses",
        show_header=True,
        header_style="bold cyan",
        padding=(0, 2),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Repository", style="bold")
    table.add_column("Timestamp", style="dim")
    table.add_column("Score", style="bold")

    for i, entry in enumerate(recent[:10], 1):
        table.add_row(
            str(i),
            entry.get("path", "?"),
            entry.get("timestamp", "?")[:19],
            entry.get("score", "N/A"),
        )

    console.print()
    console.print(table)
    console.print()
    return True


@command("/quit", "Exit interactive mode", "/quit")
def cmd_quit(args: list[str], context: dict) -> bool:
    """Exit interactive mode."""
    console.print("  [dim]Goodbye![/dim]")
    context["quit"] = True
    return False


# ── Command Parser ─────────────────────────────────────────────────────
def parse_command(line: str) -> tuple[str, list[str]]:
    """Parse a slash command line into (command, args)."""
    line = line.strip()
    if not line.startswith("/"):
        return "", [line]

    parts = line.split()
    cmd = parts[0].lower()
    args = parts[1:]
    return cmd, args


def execute_command(line: str, context: dict) -> bool:
    """Execute a slash command. Returns True to continue, False to exit."""
    cmd, args = parse_command(line)

    if not cmd:
        return True

    if cmd in COMMANDS:
        return COMMANDS[cmd]["handler"](args, context)
    else:
        console.print(f"  [red]Unknown command: {cmd}[/red]")
        console.print("  [dim]Type /help for available commands.[/dim]")
        return True


def print_welcome() -> None:
    """Print the interactive mode welcome message."""
    console.print()
    info_panel(
        "MIIE Interactive Mode",
        "Type /help for commands, or enter a repository path to begin.",
    )
    console.print()


def print_command_hint() -> None:
    """Print a subtle command hint."""
    console.print("  [dim]Type /help for commands, or enter a path to analyze.[/dim]")
