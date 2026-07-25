"""MIIE Application Layer — Presentation-independent orchestration.

This package provides the application layer that sits between the
CLI/API interface and the frozen processing layer. It owns:

- Pipeline orchestration (ApplicationService)
- Workflow execution (WorkflowEngine)
- Session management (SessionManager)
- Command routing (CommandRouter)
- Output formatting (OutputFormatter)
- Interactive navigation (InteractiveNavigator)

The scientific core (metrics, detectors, scoring, evidence) is never
modified by this layer — it is consumed through the processing layer's
public interfaces.
"""

from .navigation import Menu, MenuItem, Prompt
from .output import OutputFormatter
from .router import Command, CommandRouter
from .service import ApplicationService
from .session import Session, SessionManager
from .workflow import WorkflowEngine, WorkflowState, WorkflowStep

# Lazy import to avoid circular dependency (interactive -> service -> __init__)
# InteractiveNavigator is imported on first use, not at module load time


def __getattr__(name):
    if name == "InteractiveNavigator":
        from .interactive import InteractiveNavigator as _IN

        return _IN
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ApplicationService",
    "WorkflowEngine",
    "WorkflowStep",
    "WorkflowState",
    "SessionManager",
    "Session",
    "CommandRouter",
    "Command",
    "OutputFormatter",
    "Menu",
    "MenuItem",
    "Prompt",
    "InteractiveNavigator",
]
