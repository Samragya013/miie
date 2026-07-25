"""MIIE TUI -- Full-screen interactive terminal user interface.

Inspired by Claude Code / OpenCode / Mimo Code.
Uses Rich Layout + Live for real-time panel updates.
Non-blocking keyboard input via msvcrt (Windows) / termios (Unix).

Unified navigation model:
- Number keys (1-6): Direct panel access
- j/k or Up/Down: Sequential navigation
- Tab/Shift-Tab: Cycle panels
- Enter/Space: Expand detail
- /: Filter (future)
- ?: Toggle help overlay
- q: Quit

Entry point: launch_tui() or via `miie` with no args.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from .branding import LOGO_FULL_TALL, PALETTE_PREMIUM

# ── TUI State ──────────────────────────────────────────────────────────


class TUIState:
    """Mutable state for the TUI application."""

    def __init__(self) -> None:
        self.active_panel: str = "main"
        self.repo_path: str = "."
        self.output_dir: str = "./output"
        self.status_message: str = "Ready"
        self.main_content: str = "welcome"
        self.sidebar_selected: int = 0
        self.running: bool = True
        self.analysis_result: dict | None = None
        self.history: list[dict] = []
        self.verbose: bool = False
        # Command input mode
        self.command_mode: bool = False
        self.command_buffer: str = ""
        self.command_history: list[str] = []
        self.history_index: int = -1

    def set_main(self, content: str) -> None:
        self.main_content = content

    def set_status(self, msg: str) -> None:
        self.status_message = msg


# ── Panel Renderers ────────────────────────────────────────────────────


def _render_header(state: TUIState) -> Panel:
    """Render the header with big MIIE logo."""
    logo_lines = LOGO_FULL_TALL.strip().split("\n")
    text = Text()
    for line in logo_lines:
        text.append(f"  {line}\n", style="bold bright_cyan")
    text.append("  Measurement Integrity Intelligence Engine", style="dim white")
    return Panel(text, style="bold bright_cyan", height=len(logo_lines) + 2)


def _render_sidebar(state: TUIState) -> Panel:
    """Render sidebar with navigation items."""
    items = [
        ("[1] Dashboard", "dashboard"),
        ("[2] Analyze", "analyze"),
        ("[3] Status", "status"),
        ("[4] Config", "config"),
        ("[5] History", "history"),
        ("[6] Help", "help"),
    ]
    text = Text()
    text.append("  NAVIGATION\n", style="bold bright_cyan")
    text.append("  " + "-" * 20 + "\n", style="dim")
    for i, (label, key) in enumerate(items):
        style = "bold white on bright_cyan" if state.sidebar_selected == i else "white"
        text.append(f"  {label}\n", style=style)

    text.append("\n  RECENT\n", style="bold bright_cyan")
    text.append("  " + "-" * 20 + "\n", style="dim")
    if state.repo_path:
        text.append(f"  repo: {state.repo_path[:20]}\n", style="dim")
    text.append(f"  out:  {state.output_dir[:20]}\n", style="dim")

    return Panel(text, title="[bold]Menu[/bold]", border_style="bright_cyan", width=26)


def _render_main(state: TUIState) -> Panel:
    """Render main content area."""
    content = state.main_content

    if content == "welcome":
        return _render_welcome(state)
    elif content == "dashboard":
        return _render_dashboard(state)
    elif content == "analyze":
        return _render_analyze_view(state)
    elif content == "status":
        return _render_status_view(state)
    elif content == "config":
        return _render_config_view(state)
    elif content == "history":
        return _render_history_view(state)
    elif content == "help":
        return _render_help_view(state)
    else:
        return Panel(Text(f"  Unknown view: {content}"), title="Main")


def _render_welcome(state: TUIState) -> Panel:
    """Render welcome screen."""
    text = Text()
    text.append("\n  Welcome to MIIE\n\n", style="bold bright_cyan")
    text.append("  Measurement Integrity Intelligence Engine\n", style="dim white")
    text.append("  v" + _get_version() + "\n\n", style="dim")
    text.append("  " + "=" * 50 + "\n\n", style="dim")
    text.append("  Quick Start:\n\n", style="bold white")
    text.append("  1. Set repository:  ", style="white")
    text.append("repo /path/to/repo\n", style="bright_cyan")
    text.append("  2. Run analysis:    ", style="white")
    text.append("run\n", style="bright_cyan")
    text.append("  3. View results:    ", style="white")
    text.append("dashboard\n", style="bright_cyan")
    text.append("\n  Keyboard Shortcuts:\n\n", style="bold white")
    text.append("  j/k         ", style="bright_cyan")
    text.append("Navigate panels\n", style="white")
    text.append("  1-6         ", style="bright_cyan")
    text.append("Jump to panel\n", style="white")
    text.append("  Tab         ", style="bright_cyan")
    text.append("Cycle panels\n", style="white")
    text.append("  : or /      ", style="bright_cyan")
    text.append("Enter command mode\n", style="white")
    text.append("  ?           ", style="bright_cyan")
    text.append("Toggle help overlay\n", style="white")
    text.append("  q           ", style="bright_cyan")
    text.append("Quit\n", style="white")
    text.append("\n  Type ", style="dim")
    text.append(":", style="bright_cyan")
    text.append(" or ", style="dim")
    text.append("/", style="bright_cyan")
    text.append(" to enter command mode.\n", style="dim")
    return Panel(text, title="[bold]Welcome[/bold]", border_style="bright_cyan")


def _render_dashboard(state: TUIState) -> Panel:
    """Render dashboard with analysis overview."""
    text = Text()
    text.append("\n  DASHBOARD\n", style="bold bright_cyan")
    text.append("  " + "=" * 40 + "\n\n", style="dim")

    if state.analysis_result:
        text.append("  Last Analysis\n", style="bold white")
        text.append("  " + "-" * 30 + "\n", style="dim")
        result = state.analysis_result
        if "integrity" in result:
            score = result["integrity"]
            color = "green" if score >= 0.8 else "yellow" if score >= 0.6 else "red"
            text.append(f"  Integrity: ", style="white")
            text.append(f"{score:.2f}\n", style=f"bold {color}")
        if "confidence" in result:
            text.append(f"  Confidence: ", style="white")
            text.append(f"{result['confidence']:.2f}\n", style="bold white")
    else:
        text.append("  No analysis results yet.\n\n", style="dim")
        text.append("  Run ", style="white")
        text.append("analyze", style="bright_cyan")
        text.append(" to start.\n", style="white")

    text.append("\n  System\n", style="bold white")
    text.append("  " + "-" * 30 + "\n", style="dim")
    text.append(f"  Version:  {_get_version()}\n", style="dim")
    text.append(f"  Platform: {sys.platform}\n", style="dim")
    text.append(f"  Python:   {sys.version.split()[0]}\n", style="dim")

    return Panel(text, title="[bold]Dashboard[/bold]", border_style="bright_cyan")


def _render_analyze_view(state: TUIState) -> Panel:
    """Render analyze view."""
    text = Text()
    text.append("\n  ANALYZE\n", style="bold bright_cyan")
    text.append("  " + "=" * 40 + "\n\n", style="dim")
    text.append(f"  Repository:  ", style="white")
    text.append(f"{state.repo_path}\n", style="bright_cyan")
    text.append(f"  Output:      ", style="white")
    text.append(f"{state.output_dir}\n", style="bright_cyan")
    text.append("\n  Type ", style="dim")
    text.append("analyze", style="bright_cyan")
    text.append(" in command bar to run.\n", style="dim")
    text.append("  Or use: ", style="dim")
    text.append("analyze /path/to/repo\n", style="bright_cyan")
    return Panel(text, title="[bold]Analyze[/bold]", border_style="bright_cyan")


def _render_status_view(state: TUIState) -> Panel:
    """Render system status."""
    text = Text()
    text.append("\n  SYSTEM STATUS\n", style="bold bright_cyan")
    text.append("  " + "=" * 40 + "\n\n", style="dim")
    text.append("  Engines\n", style="bold white")
    text.append("  " + "-" * 30 + "\n", style="dim")

    engines = [
        "IngestionEngine",
        "ExtractionEngine",
        "SegmentationEngine",
        "ScoringEngine",
        "EvidenceEngine",
        "ExplanationEngine",
        "ReportGenerator",
        "BenchmarkEngine",
        "EvaluationEngine",
    ]
    _engine_modules = {
        "IngestionEngine": "miie.processing.ingestion",
        "ExtractionEngine": "miie.processing.extraction",
        "SegmentationEngine": "miie.processing.segmentation",
        "ScoringEngine": "miie.processing.scoring.engine",
        "EvidenceEngine": "miie.processing.evidence",
        "ExplanationEngine": "miie.processing.explanation.engine",
        "ReportGenerator": "miie.processing.reporting.engine",
        "BenchmarkEngine": "miie.processing.benchmark.engine",
        "EvaluationEngine": "miie.processing.evaluation.engine",
    }
    for eng in engines:
        try:
            __import__(_engine_modules[eng])
            text.append(f"  [OK]  ", style="bold green")
            text.append(f"{eng}\n", style="white")
        except Exception:
            text.append(f"  [!!]  ", style="bold red")
            text.append(f"{eng}\n", style="dim red")

    return Panel(text, title="[bold]Status[/bold]", border_style="bright_cyan")


def _render_config_view(state: TUIState) -> Panel:
    """Render config view."""
    text = Text()
    text.append("\n  CONFIGURATION\n", style="bold bright_cyan")
    text.append("  " + "=" * 40 + "\n\n", style="dim")
    text.append(f"  repo_path:  {state.repo_path}\n", style="white")
    text.append(f"  output_dir: {state.output_dir}\n", style="white")
    text.append(f"  verbose:    {state.verbose}\n", style="white")
    text.append("\n  Use ", style="dim")
    text.append("config", style="bright_cyan")
    text.append(" command to modify.\n", style="dim")
    return Panel(text, title="[bold]Config[/bold]", border_style="bright_cyan")


def _render_history_view(state: TUIState) -> Panel:
    """Render history view."""
    text = Text()
    text.append("\n  HISTORY\n", style="bold bright_cyan")
    text.append("  " + "=" * 40 + "\n\n", style="dim")
    if state.history:
        for i, entry in enumerate(state.history[-10:], 1):
            text.append(f"  {i}. ", style="bold white")
            text.append(f"{entry.get('repo', '?')}\n", style="dim")
            text.append(f"     ", style="dim")
            text.append(f"{entry.get('timestamp', '?')}\n", style="dim")
    else:
        text.append("  No history yet.\n", style="dim")
    return Panel(text, title="[bold]History[/bold]", border_style="bright_cyan")


def _render_help_view(state: TUIState) -> Panel:
    """Render help overlay with keyboard shortcuts."""
    text = Text()
    text.append("\n  KEYBOARD SHORTCUTS\n", style="bold bright_cyan")
    text.append("  " + "=" * 44 + "\n\n", style="dim")
    shortcuts = [
        (
            "Navigation",
            [
                ("j / Down", "Next panel"),
                ("k / Up", "Previous panel"),
                ("1-6", "Jump to panel"),
                ("Tab", "Cycle panels"),
            ],
        ),
        (
            "Actions",
            [
                (": or /", "Enter command mode"),
                ("Enter", "Execute command"),
                ("?", "Toggle this help"),
                ("q", "Quit"),
            ],
        ),
        (
            "Commands",
            [
                ("repo <path>", "Set repository"),
                ("run", "Start analysis"),
                ("dashboard", "Show results"),
                ("status", "System status"),
                ("config", "Configuration"),
                ("history", "Past runs"),
                ("help", "Show help"),
            ],
        ),
    ]
    for section, items in shortcuts:
        text.append(f"  {section}\n", style="bold white")
        text.append("  " + "-" * 30 + "\n", style="dim")
        for key, desc in items:
            text.append(f"    {key:14s}", style="bold bright_cyan")
            text.append(f" {desc}\n", style="white")
        text.append("\n", style="dim")

    text.append("  Press ", style="dim")
    text.append("?", style="bold bright_cyan")
    text.append(" or ", style="dim")
    text.append("q", style="bold bright_cyan")
    text.append(" to close.\n", style="dim")

    return Panel(text, title="[bold]Help[/bold]", border_style="bright_cyan")


def _render_status_bar(state: TUIState) -> Panel:
    """Render status bar with command input."""
    text = Text()
    text.append("  MIIE ", style="bold bright_cyan")

    if hasattr(state, "command_mode") and state.command_mode:
        text.append(":", style="bold bright_cyan")
        text.append(getattr(state, "command_buffer", ""), style="bold white")
        text.append("_", style="blink white")
        text.append("  Enter: execute  Esc: cancel", style="dim")
    else:
        text.append(state.status_message, style="white")
        text.append("  j/k: nav  ?: help  q: quit", style="dim")

    return Panel(text, style="dim", height=1)


def _get_version() -> str:
    """Get MIIE version."""
    try:
        from miie import __version__

        return __version__
    except ImportError:
        return "1.6.0"


# ── Layout Builder ─────────────────────────────────────────────────────


def _build_layout(state: TUIState) -> Layout:
    """Build the TUI layout."""
    layout = Layout()

    layout.split_column(
        Layout(_render_header(state), name="header", size=10),
        Layout(name="body"),
        Layout(_render_status_bar(state), name="footer", size=1),
    )

    layout["body"].split_row(
        Layout(_render_sidebar(state), name="sidebar", size=26),
        Layout(_render_main(state), name="main"),
    )

    return layout


# ── Keyboard Handler ───────────────────────────────────────────────────


def _handle_key(state: TUIState, key: str) -> bool:
    """Handle keyboard input. Returns False to quit.

    Unified navigation model (inspired by LazyGit / K9s / gh CLI):
    - Number keys (1-6): Direct panel access
    - j/k or Up/Down: Sequential navigation
    - Tab/Shift-Tab: Cycle panels
    - Enter/Space: Expand detail
    - /: Filter (future)
    - ?: Toggle help overlay
    - q: Quit
    """

    # Command input mode - handle text input
    if state.command_mode:
        if key == "escape":
            state.command_mode = False
            state.command_buffer = ""
            state.set_status("Ready")
            return True
        elif key == "enter":
            cmd = state.command_buffer.strip()
            if cmd:
                state.command_history.append(cmd)
                state.history_index = len(state.command_history)
                _execute_tui_command(state, cmd)
            state.command_mode = False
            state.command_buffer = ""
            return True
        elif key == "backspace":
            state.command_buffer = state.command_buffer[:-1]
            state.set_status(f": {state.command_buffer}")
            return True
        elif key == "up":
            if state.history_index > 0:
                state.history_index -= 1
                state.command_buffer = state.command_history[state.history_index]
                state.set_status(f": {state.command_buffer}")
            return True
        elif key == "down":
            if state.history_index < len(state.command_history) - 1:
                state.history_index += 1
                state.command_buffer = state.command_history[state.history_index]
            else:
                state.history_index = len(state.command_history)
                state.command_buffer = ""
            state.set_status(f": {state.command_buffer}")
            return True
        elif len(key) == 1 and key.isprintable():
            state.command_buffer += key
            state.set_status(f": {state.command_buffer}")
            return True
        return True

    # Normal mode
    if key == "q" or key == "ctrl-c":
        state.running = False
        return False

    # Enter command mode with : or /
    if key in (":", "/"):
        state.command_mode = True
        state.command_buffer = ""
        state.history_index = len(state.command_history)
        state.set_status(":")
        return True

    # ? toggles help overlay (replaces non-functional Ctrl+K palette)
    if key == "?":
        if state.main_content == "help":
            state.set_main("welcome")
            state.set_status("Ready")
        else:
            state.set_main("help")
            state.set_status("Help - press ? to close")
        return True

    # Ctrl+K now also toggles help (unified with ?)
    if key == "ctrl+k":
        if state.main_content == "help":
            state.set_main("welcome")
            state.set_status("Ready")
        else:
            state.set_main("help")
            state.set_status("Help - press ? to close")
        return True

    if key == "escape":
        if state.main_content == "help":
            state.set_main("welcome")
            state.set_status("Ready")
        return True

    # Tab / Shift-Tab cycle panels
    if key == "tab":
        panels = ["welcome", "dashboard", "analyze", "status", "config", "history", "help"]
        try:
            idx = panels.index(state.main_content)
            state.set_main(panels[(idx + 1) % len(panels)])
        except ValueError:
            state.set_main("welcome")
        # Update sidebar selection to match
        try:
            state.sidebar_selected = panels.index(state.main_content)
        except ValueError:
            pass
        return True

    # j / Down: next panel
    if key in ("j", "down"):
        panels = ["welcome", "dashboard", "analyze", "status", "config", "history", "help"]
        state.sidebar_selected = min(len(panels) - 1, state.sidebar_selected + 1)
        state.set_main(panels[state.sidebar_selected])
        return True

    # k / Up: previous panel
    if key in ("k", "up"):
        panels = ["welcome", "dashboard", "analyze", "status", "config", "history", "help"]
        state.sidebar_selected = max(0, state.sidebar_selected - 1)
        state.set_main(panels[state.sidebar_selected])
        return True

    # Number keys: direct panel access
    if key in ("1", "2", "3", "4", "5", "6"):
        panel_map = {
            "1": "dashboard",
            "2": "analyze",
            "3": "status",
            "4": "config",
            "5": "history",
            "6": "help",
        }
        state.set_main(panel_map[key])
        state.sidebar_selected = int(key) - 1
        return True

    return True


# ── Command Execution ──────────────────────────────────────────────────


# ── In-Process Analysis ─────────────────────────────────────────────────


def _run_tui_analysis(state: TUIState) -> None:
    """Run the MIIE pipeline in-process with progress updates.

    Unlike the subprocess approach, this streams progress updates directly
    to the TUI status bar, keeping the UI responsive during analysis.
    """
    import time as _time

    state.set_status("Starting analysis pipeline...")

    try:
        t0 = _time.perf_counter()

        # Stage 1: Acquisition
        state.set_status("[1/6] Loading repository...")
        from ..processing.ingestion import RepositoryIngestionEngine

        ingestion = RepositoryIngestionEngine()
        repo_context = ingestion.ingest(state.repo_path)
        total_commits = getattr(repo_context, "total_commits", "?")
        state.set_status(f"[1/6] Loaded {total_commits} commits ({_time.perf_counter() - t0:.1f}s)")

        # Stage 2: Extraction
        state.set_status("[2/6] Extracting metrics...")
        t_stage = _time.perf_counter()
        from ..processing.extraction.engine import ExtractionEngine

        extraction = ExtractionEngine()
        observation_collection, metric_dataframe = extraction.extract(
            context=repo_context,
            metric_list=["M-02", "M-06"],
        )
        state.set_status(f"[2/6] Metrics extracted ({_time.perf_counter() - t_stage:.1f}s)")

        # Stage 3: Segmentation
        state.set_status("[3/6] Building windows...")
        t_stage = _time.perf_counter()
        from ..processing.observation.models import WindowConfig
        from ..processing.observation.window_builder import ObservationWindowBuilder

        builder = ObservationWindowBuilder()
        window_config = WindowConfig(
            strategy="temporal",
            window_size=7,
            min_observations=2,
        )
        builder_result = builder.build(collection=observation_collection, config=window_config)
        observation_windows = builder_result.windows
        state.set_status(f"[3/6] {len(observation_windows)} windows ({_time.perf_counter() - t_stage:.1f}s)")

        # Stage 4: Detection
        state.set_status("[4/6] Running detectors...")
        t_stage = _time.perf_counter()
        from ..processing.detection.dispatcher import DetectorDispatcherEngine

        dispatcher = DetectorDispatcherEngine()
        detections = dispatcher.dispatch(
            metric_dataframe=metric_dataframe,
            window_config=window_config,
            observation_collection=observation_collection,
        )
        state.set_status(f"[4/6] {len(detections)} detections ({_time.perf_counter() - t_stage:.1f}s)")

        # Stage 5: Scoring
        state.set_status("[5/6] Computing scores...")
        t_stage = _time.perf_counter()
        from ..processing.scoring.engine import ScoringEngine

        scoring = ScoringEngine()
        integrity_score = scoring.compute_integrity(detections=detections)
        confidence_score = scoring.compute_confidence(
            observation_count=sum(len(ow.observations) for ow in observation_windows),
            window_count=len(observation_windows),
            detection_count=len(detections),
        )
        state.set_status(f"[5/6] Scores computed ({_time.perf_counter() - t_stage:.1f}s)")

        # Stage 6: Report
        state.set_status("[6/6] Generating report...")
        t_stage = _time.perf_counter()
        from ..processing.reporting.engine import ReportGenerator

        report_gen = ReportGenerator()
        report = report_gen.generate(
            integrity_score=integrity_score,
            confidence_score=confidence_score,
            detections=detections,
            output_dir=state.output_dir,
        )
        state.set_status(f"[6/6] Report saved ({_time.perf_counter() - t_stage:.1f}s)")

        # Store results
        state.analysis_result = {
            "integrity": getattr(integrity_score, "score", None),
            "confidence": getattr(confidence_score, "score", None),
            "detections": len(detections),
            "windows": len(observation_windows),
            "commits": total_commits,
        }

        # Populate history
        state.history.append(
            {
                "repo": state.repo_path,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "integrity": state.analysis_result.get("integrity"),
                "confidence": state.analysis_result.get("confidence"),
                "detections": len(detections),
            }
        )

        elapsed = _time.perf_counter() - t0
        state.set_status(f"Complete! {len(detections)} detections, {elapsed:.1f}s total")
        state.set_main("dashboard")

    except Exception as e:
        state.set_status(f"Error: {e}")
        # Still record the attempt in history
        state.history.append(
            {
                "repo": state.repo_path,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "error": str(e),
            }
        )


def _execute_tui_command(state: TUIState, cmd: str) -> None:
    """Execute a command entered in the TUI."""
    # Parse command
    parts = cmd.split()
    if not parts:
        return

    command = parts[0].lower()
    args = parts[1:]

    if command in ("help", "h", "?"):
        state.set_main("help")
        state.set_status("Help")

    elif command in ("quit", "exit", "q"):
        state.running = False

    elif command in ("dashboard", "dash", "d"):
        state.set_main("dashboard")
        state.set_status("Dashboard")

    elif command in ("analyze", "a"):
        if args:
            state.repo_path = args[0]
        state.set_main("analyze")
        state.set_status(f"Analyze: {state.repo_path}")

    elif command in ("status", "s"):
        state.set_main("status")
        state.set_status("Status")

    elif command in ("config", "c"):
        state.set_main("config")
        state.set_status("Config")

    elif command in ("history", "hist", "h"):
        state.set_main("history")
        state.set_status("History")

    elif command == "repo":
        if args:
            state.repo_path = args[0]
            state.set_status(f"Repository: {state.repo_path}")
        else:
            state.set_status(f"Repository: {state.repo_path}")

    elif command == "output":
        if args:
            state.output_dir = args[0]
            state.set_status(f"Output: {state.output_dir}")
        else:
            state.set_status(f"Output: {state.output_dir}")

    elif command == "run":
        state.set_status("Running analysis...")
        state.set_main("analyze")
        _run_tui_analysis(state)

    elif command == "cls" or command == "clear":
        # Clear is handled by Rich Live refresh
        state.set_status("Cleared")

    else:
        state.set_status(f"Unknown command: {command} (type help for commands)")


# ── Input Reader ───────────────────────────────────────────────────────


def _read_key() -> str:
    """Read a single keypress (non-blocking on supported terminals)."""
    # Windows: msvcrt
    try:
        import msvcrt

        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch in (b"\x03", b"\x1b"):  # Ctrl+C or Esc
                return "q" if ch == b"\x03" else "escape"
            if ch == b"\t":
                return "tab"
            if ch in (b"\r",):
                return "enter"
            if ch == b"\x08":  # Backspace
                return "backspace"
            if ch == b"\x7f":  # Delete (some terminals)
                return "backspace"
            if ch == b"\x00" or ch == b"\xe0":  # Special key prefix
                ch2 = msvcrt.getch()
                if ch2 == b"H":
                    return "up"
                if ch2 == b"P":
                    return "down"
                if ch2 == b"K":
                    return "left"
                if ch2 == b"M":
                    return "right"
                return ""
            # Ctrl+K = 0x0B on Windows
            if ch == b"\x0b":
                return "ctrl+k"
            try:
                return ch.decode("utf-8", errors="replace")
            except Exception:
                return ""
    except ImportError:
        pass

    # Unix: termios
    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x03":
                return "q"
            if ch == "\x0b":  # Ctrl+K
                return "ctrl+k"
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":
                        return "up"
                    if ch3 == "B":
                        return "down"
                    if ch3 == "C":
                        return "right"
                    if ch3 == "D":
                        return "left"
                return "escape"
            if ch == "\t":
                return "tab"
            if ch == "\r":
                return "enter"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass

    return ""


# ── TUI Application ───────────────────────────────────────────────────


class MIIETuiApp:
    """Full-screen TUI application for MIIE."""

    def __init__(self) -> None:
        self.state = TUIState()
        self.console = Console()

    def run(self) -> None:
        """Run the TUI main loop."""
        # Animated splash
        from .tui_splash import play_splash

        play_splash(self.console)

        # Main loop
        with Live(
            _build_layout(self.state),
            console=self.console,
            refresh_per_second=10,
            screen=True,
        ) as live:
            while self.state.running:
                try:
                    key = _read_key()
                    if key:
                        _handle_key(self.state, key)
                        live.update(_build_layout(self.state))
                    else:
                        time.sleep(0.05)
                except KeyboardInterrupt:
                    self.state.running = False
                except Exception:
                    time.sleep(0.1)

        self.console.clear()
        self.console.print("  [dim]Goodbye![/dim]")


def launch_tui() -> None:
    """Launch the MIIE TUI."""
    app = MIIETuiApp()
    app.run()
