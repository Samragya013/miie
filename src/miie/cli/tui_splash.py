"""MIIE TUI Splash -- Animated logo reveal for the TUI."""

from __future__ import annotations

import time

from rich.console import Console
from rich.text import Text

from .branding import LOGO_FULL_TALL, PALETTE_PREMIUM


def _poll_key_nonblocking() -> str:
    """Check for a keypress without blocking. Returns the key or empty string."""
    try:
        import msvcrt

        if msvcrt.kbhit():
            return msvcrt.getwch()
    except ImportError:
        pass
    return ""


def play_splash(console: Console | None = None, delay: float = 0.6) -> None:
    """Play animated splash with big MIIE logo reveal.

    Line-by-line reveal with alternating colors and subtle glow.
    Press any key to skip the remaining animation.
    """
    if console is None:
        console = Console()

    pal = PALETTE_PREMIUM
    logo_lines = LOGO_FULL_TALL.strip().split("\n")
    total = len(logo_lines)

    # Clear
    if console.is_terminal:
        console.clear()

    # Reveal logo line by line (skippable)
    line_delay = delay / total if delay > 0 else 0
    for i, line in enumerate(logo_lines):
        # Check for keypress to skip
        if _poll_key_nonblocking():
            # Flush remaining lines instantly
            for remaining in logo_lines[i:]:
                text = Text()
                text.append(f"  {remaining}", style=pal["logo"])
                console.print(text)
            break
        text = Text()
        # Alternate between main and accent colors
        style = pal["logo"] if i % 3 == 0 else pal["logo_accent"] if i % 3 == 1 else pal["glow"]
        text.append(f"  {line}", style=style)
        console.print(text)
        if line_delay > 0:
            time.sleep(line_delay)

    # Version + subtitle
    console.print()
    ver_text = Text()
    try:
        from miie import __version__

        ver = __version__
    except ImportError:
        ver = "1.6.0"
    ver_text.append(f"  v{ver}", style=pal["version"])
    ver_text.append("  Measurement Integrity Intelligence Engine", style=pal["tagline"])
    console.print(ver_text)

    # Separator
    console.print()
    sep = Text()
    sep.append("  " + "=" * 56, style=pal["border"])
    console.print(sep)
    console.print()

    # Brief pause — also skippable
    if delay > 0:
        # Wait up to 0.3s, but bail on keypress
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            if _poll_key_nonblocking():
                break
            time.sleep(0.02)
