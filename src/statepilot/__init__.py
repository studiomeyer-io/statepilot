"""statepilot — deterministic state-machine guards for AI-agent workflows.

Define a state machine, then enforce at *runtime* which tools an agent may call,
in which order, with loop detection, a cost budget, and a hard step cap.

Quickstart::

    from statepilot import StateMachine, Pilot, guarded

    machine = (
        StateMachine.builder()
        .initial("research")
        .transition("research", "research", tool="search")   # loop allowed...
        .transition("research", "draft", tool="write_draft")
        .transition("draft", "review", tool="review")
        .transition("review", "published", tool="publish")
        .terminal("published")
        .build()
    )

    pilot = Pilot(machine, budget=5.0, max_state_visits=3)

    @guarded(pilot, cost=1.0)
    def search(q: str) -> str:
        ...

    search("agents")          # allowed, charges 1.0
    pilot.step("write_draft") # advance to draft
"""

from __future__ import annotations

from .__about__ import __version__
from .decorator import guarded
from .exceptions import (
    BudgetExceeded,
    GuardViolation,
    LoopLimitExceeded,
    StateMachineError,
    StatepilotError,
    StepLimitExceeded,
    TransitionError,
)
from .machine import StateMachine, StateMachineBuilder, Transition
from .pilot import Pilot, StepRecord

__all__ = [
    "__version__",
    # core
    "Pilot",
    "StateMachine",
    "StateMachineBuilder",
    "StepRecord",
    "Transition",
    "guarded",
    # exceptions
    "BudgetExceeded",
    "GuardViolation",
    "LoopLimitExceeded",
    "StateMachineError",
    "StatepilotError",
    "StepLimitExceeded",
    "TransitionError",
]
