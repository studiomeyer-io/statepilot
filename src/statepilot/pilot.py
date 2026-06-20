"""The runtime guard: :class:`Pilot`.

A :class:`Pilot` wraps a :class:`statepilot.machine.StateMachine` and holds the
*live* state of one agent run. Every tool call must go through :meth:`Pilot.step`
(directly or via the :func:`guarded` decorator). The pilot:

* refuses tool calls that are not allowed from the current state
  (:class:`~statepilot.exceptions.TransitionError`),
* refuses to leave a terminal state,
* enforces a loop limit (per-state visits and consecutive-tool repeats),
* enforces a cumulative cost budget, and
* enforces a hard cap on the total number of steps.

It records every accepted step in :attr:`Pilot.history` and can export a trace
for logging or assertions in tests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .exceptions import (
    BudgetExceeded,
    LoopLimitExceeded,
    StepLimitExceeded,
    TransitionError,
)
from .machine import StateMachine

__all__ = ["Pilot", "StepRecord"]

# Budget comparisons are forgiving by one tiny epsilon so that accumulating
# e.g. 0.1 ten times does not spuriously trip a budget of exactly 1.0.
_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class StepRecord:
    """One accepted transition in a pilot's history.

    Attributes:
        index: Zero-based position of this step in the run.
        tool: The tool/event that triggered the transition.
        source: State before the transition.
        dest: State after the transition.
        cost: Cost attributed to this step.
        cumulative_cost: Total cost spent up to and including this step.
        timestamp: ``time.time()`` when the step was accepted.
    """

    index: int
    tool: str
    source: str
    dest: str
    cost: float
    cumulative_cost: float
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable view of this step."""
        return {
            "index": self.index,
            "tool": self.tool,
            "source": self.source,
            "dest": self.dest,
            "cost": self.cost,
            "cumulative_cost": self.cumulative_cost,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class Pilot:
    """Stateful runtime enforcer for a :class:`StateMachine`.

    Args:
        machine: The state machine to enforce.
        budget: Optional cumulative cost cap. ``None`` disables the budget guard.
        max_steps: Optional hard cap on total accepted steps. ``None`` disables it.
        max_state_visits: Optional cap on how often any single state may be
            entered (loop guard). ``None`` disables per-state loop detection.
        max_consecutive_tool: Optional cap on how many times the *same* tool may
            be invoked back-to-back (loop guard). ``None`` disables it.

    The pilot starts in ``machine.initial``. Use :meth:`step` to advance it.
    """

    machine: StateMachine
    budget: float | None = None
    max_steps: int | None = None
    max_state_visits: int | None = None
    max_consecutive_tool: int | None = None

    state: str = field(init=False)
    cost_spent: float = field(init=False, default=0.0)
    _history: list[StepRecord] = field(init=False, default_factory=list)
    _state_visits: dict[str, int] = field(init=False, default_factory=dict)
    _last_tool: str | None = field(init=False, default=None)
    _consecutive_tool: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if self.budget is not None and self.budget < 0:
            raise ValueError("budget must be >= 0 or None.")
        if self.max_steps is not None and self.max_steps < 0:
            raise ValueError("max_steps must be >= 0 or None.")
        if self.max_state_visits is not None and self.max_state_visits < 1:
            raise ValueError("max_state_visits must be >= 1 or None.")
        if self.max_consecutive_tool is not None and self.max_consecutive_tool < 1:
            raise ValueError("max_consecutive_tool must be >= 1 or None.")
        self.state = self.machine.initial
        # The initial state counts as one visit so loop limits include the start.
        self._state_visits[self.state] = 1

    # -- introspection ----------------------------------------------------

    @property
    def steps_taken(self) -> int:
        """Number of accepted steps so far."""
        return len(self._history)

    @property
    def history(self) -> tuple[StepRecord, ...]:
        """Immutable snapshot of accepted steps (oldest first).

        Returned as a tuple so external code can't desync the run by mutating
        it — the step-limit guard counts from the pilot's own internal record.
        """
        return tuple(self._history)

    @property
    def done(self) -> bool:
        """``True`` if the pilot is currently in a terminal state."""
        return self.machine.is_terminal(self.state)

    def allowed_tools(self) -> tuple[str, ...]:
        """Tools allowed from the current state (empty when terminal)."""
        return self.machine.allowed_tools(self.state)

    def can(self, tool: str, *, cost: float = 0.0) -> bool:
        """Return ``True`` if :meth:`step` would currently accept ``tool``.

        Pure check — never mutates state and never raises for a guard violation.
        (Like :meth:`step`, a negative ``cost`` is a programming error and raises
        :class:`ValueError` — that is an invalid argument, not a guard decision.)
        Useful for letting an agent *plan* before acting.
        """
        if cost < 0:
            raise ValueError("cost must be >= 0.")
        if self.machine.is_terminal(self.state):
            return False
        dest = self.machine.resolve(self.state, tool)
        if dest is None:
            return False
        if self.max_steps is not None and self.steps_taken + 1 > self.max_steps:
            return False
        if self.budget is not None and self.cost_spent + cost > self.budget + _EPSILON:
            return False
        if (
            self.max_consecutive_tool is not None
            and tool == self._last_tool
            and self._consecutive_tool + 1 > self.max_consecutive_tool
        ):
            return False
        return not (
            self.max_state_visits is not None
            and self._state_visits.get(dest, 0) + 1 > self.max_state_visits
        )

    # -- the one method that matters --------------------------------------

    def step(self, tool: str, *, cost: float = 0.0) -> str:
        """Validate and apply one tool call. Returns the new state.

        Order of checks (fail fast, most fundamental first):

        1. terminal state -> :class:`TransitionError`
        2. transition allowed? -> :class:`TransitionError`
        3. step limit -> :class:`StepLimitExceeded`
        4. budget -> :class:`BudgetExceeded`
        5. consecutive-tool loop -> :class:`LoopLimitExceeded`
        6. per-state loop -> :class:`LoopLimitExceeded`

        On success the state advances, cost and counters update, and a
        :class:`StepRecord` is appended to :attr:`history`. On any violation the
        pilot's state is left unchanged.
        """
        if cost < 0:
            raise ValueError("cost must be >= 0.")

        source = self.state

        if self.machine.is_terminal(source):
            raise TransitionError(tool=tool, state=source, allowed=())

        dest = self.machine.resolve(source, tool)
        if dest is None:
            raise TransitionError(
                tool=tool,
                state=source,
                allowed=self.machine.allowed_tools(source),
            )

        next_step_number = self.steps_taken + 1
        if self.max_steps is not None and next_step_number > self.max_steps:
            raise StepLimitExceeded(steps=next_step_number, limit=self.max_steps)

        prospective_cost = self.cost_spent + cost
        if self.budget is not None and prospective_cost > self.budget + _EPSILON:
            raise BudgetExceeded(spent=self.cost_spent, cost=cost, budget=self.budget)

        prospective_consecutive = (
            self._consecutive_tool + 1 if tool == self._last_tool else 1
        )
        if (
            self.max_consecutive_tool is not None
            and prospective_consecutive > self.max_consecutive_tool
        ):
            raise LoopLimitExceeded(
                kind="tool",
                name=tool,
                count=prospective_consecutive,
                limit=self.max_consecutive_tool,
            )

        prospective_visits = self._state_visits.get(dest, 0) + 1
        if (
            self.max_state_visits is not None
            and prospective_visits > self.max_state_visits
        ):
            raise LoopLimitExceeded(
                kind="state",
                name=dest,
                count=prospective_visits,
                limit=self.max_state_visits,
            )

        # All guards passed — commit.
        self.cost_spent = prospective_cost
        self._consecutive_tool = prospective_consecutive
        self._last_tool = tool
        self._state_visits[dest] = prospective_visits
        self.state = dest
        record = StepRecord(
            index=self.steps_taken,
            tool=tool,
            source=source,
            dest=dest,
            cost=cost,
            cumulative_cost=self.cost_spent,
            timestamp=time.time(),
        )
        self._history.append(record)
        return dest

    # -- trace / reset ----------------------------------------------------

    def to_trace(self) -> dict[str, Any]:
        """Export a JSON-serialisable trace of the whole run.

        Shape::

            {
              "initial": "<initial state>",
              "state": "<current state>",
              "done": <bool>,
              "steps_taken": <int>,
              "cost_spent": <float>,
              "budget": <float | None>,
              "limits": {"max_steps", "max_state_visits", "max_consecutive_tool"},
              "history": [ {<StepRecord.to_dict()>}, ... ],
            }
        """
        return {
            "initial": self.machine.initial,
            "state": self.state,
            "done": self.done,
            "steps_taken": self.steps_taken,
            "cost_spent": self.cost_spent,
            "budget": self.budget,
            "limits": {
                "max_steps": self.max_steps,
                "max_state_visits": self.max_state_visits,
                "max_consecutive_tool": self.max_consecutive_tool,
            },
            "history": [record.to_dict() for record in self._history],
        }

    def reset(self) -> None:
        """Reset to the initial state, clearing cost, counters and history."""
        self.state = self.machine.initial
        self.cost_spent = 0.0
        self._history.clear()
        self._state_visits = {self.state: 1}
        self._last_tool = None
        self._consecutive_tool = 0
