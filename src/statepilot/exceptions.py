"""Exception hierarchy for statepilot.

All runtime guard violations derive from :class:`GuardViolation`, so callers can
catch the whole class of "the agent tried to do something the state machine
forbids" with a single ``except``. Definition-time problems (bad state machine
spec) raise :class:`StateMachineError` instead.
"""

from __future__ import annotations

__all__ = [
    "BudgetExceeded",
    "GuardViolation",
    "LoopLimitExceeded",
    "StateMachineError",
    "StatepilotError",
    "StepLimitExceeded",
    "TransitionError",
]


class StatepilotError(Exception):
    """Base class for every error raised by statepilot."""


class StateMachineError(StatepilotError):
    """Raised when a state machine definition is invalid.

    This is a *definition-time* error (unknown state, duplicate transition,
    missing initial state, …). It is not a guard violation — the machine itself
    is malformed.
    """


class GuardViolation(StatepilotError):
    """Base class for all *runtime* guard violations.

    Catch this to treat "the agent broke a rule" uniformly, regardless of
    whether it was a forbidden transition, a loop, a budget overrun, or too many
    steps.
    """


class TransitionError(GuardViolation):
    """Raised when a tool/event is not allowed from the current state."""

    def __init__(self, tool: str, state: str, allowed: tuple[str, ...]) -> None:
        self.tool = tool
        self.state = state
        self.allowed = allowed
        allowed_str = ", ".join(sorted(allowed)) if allowed else "<none>"
        super().__init__(
            f"Tool '{tool}' is not allowed in state '{state}'. "
            f"Allowed tools here: {allowed_str}."
        )


class LoopLimitExceeded(GuardViolation):
    """Raised when a state or tool repeats more often than the configured limit."""

    def __init__(self, kind: str, name: str, count: int, limit: int) -> None:
        self.kind = kind
        self.name = name
        self.count = count
        self.limit = limit
        super().__init__(
            f"Loop limit exceeded: {kind} '{name}' would reach {count} "
            f"occurrences (limit {limit})."
        )


class BudgetExceeded(GuardViolation):
    """Raised when the cumulative cost would exceed the configured budget."""

    def __init__(self, spent: float, cost: float, budget: float) -> None:
        self.spent = spent
        self.cost = cost
        self.budget = budget
        super().__init__(
            f"Budget exceeded: spent {spent} + {cost} would exceed budget {budget}."
        )


class StepLimitExceeded(GuardViolation):
    """Raised when the total number of steps would exceed ``max_steps``."""

    def __init__(self, steps: int, limit: int) -> None:
        self.steps = steps
        self.limit = limit
        super().__init__(
            f"Step limit exceeded: step {steps} would exceed max_steps {limit}."
        )
