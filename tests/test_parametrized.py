"""Parametrized end-to-end tests across several machine definitions.

Each case defines a machine (via dict so it is concise), a sequence of
``(tool, cost)`` steps, optional pilot limits, and the expected outcome — either
a final state, or an exception type raised at a specific step index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from statepilot import (
    BudgetExceeded,
    GuardViolation,
    LoopLimitExceeded,
    Pilot,
    StateMachine,
    StepLimitExceeded,
    TransitionError,
)


@dataclass
class Case:
    name: str
    definition: dict[str, Any]
    steps: list[tuple[str, float]]
    limits: dict[str, Any] = field(default_factory=dict)
    expect_final_state: str | None = None
    expect_error: type[GuardViolation] | None = None


_TRAFFIC = {
    "initial": "red",
    "transitions": [
        {"from": "red", "to": "green", "tool": "go"},
        {"from": "green", "to": "yellow", "tool": "caution"},
        {"from": "yellow", "to": "red", "tool": "stop"},
    ],
}

_PIPELINE = {
    "initial": "research",
    "terminal": ["published"],
    "transitions": [
        {"from": "research", "to": "research", "tool": "search"},
        {"from": "research", "to": "draft", "tool": "write_draft"},
        {"from": "draft", "to": "review", "tool": "review"},
        {"from": "review", "to": "published", "tool": "publish"},
    ],
}

_APPROVAL = {
    "initial": "submitted",
    "terminal": ["approved", "rejected"],
    "transitions": [
        {"from": "submitted", "to": "approved", "tool": "approve"},
        {"from": "submitted", "to": "rejected", "tool": "reject"},
    ],
}

CASES = [
    Case(
        name="traffic-light-cycle",
        definition=_TRAFFIC,
        steps=[("go", 0.0), ("caution", 0.0), ("stop", 0.0), ("go", 0.0)],
        expect_final_state="green",
    ),
    Case(
        name="pipeline-happy-path",
        definition=_PIPELINE,
        steps=[
            ("search", 0.0),
            ("write_draft", 0.0),
            ("review", 0.0),
            ("publish", 0.0),
        ],
        expect_final_state="published",
    ),
    Case(
        name="pipeline-forbidden-publish-early",
        definition=_PIPELINE,
        steps=[("publish", 0.0)],
        expect_error=TransitionError,
    ),
    Case(
        name="pipeline-loop-limit",
        definition=_PIPELINE,
        steps=[("search", 0.0), ("search", 0.0), ("search", 0.0)],
        limits={"max_state_visits": 3},  # initial visit + 2 searches == 3
        expect_error=LoopLimitExceeded,
    ),
    Case(
        name="pipeline-budget",
        definition=_PIPELINE,
        steps=[("search", 3.0), ("search", 3.0)],
        limits={"budget": 5.0},
        expect_error=BudgetExceeded,
    ),
    Case(
        name="pipeline-step-limit",
        definition=_PIPELINE,
        steps=[("search", 0.0), ("search", 0.0), ("search", 0.0)],
        limits={"max_steps": 2},
        expect_error=StepLimitExceeded,
    ),
    Case(
        name="approval-approve",
        definition=_APPROVAL,
        steps=[("approve", 0.0)],
        expect_final_state="approved",
    ),
    Case(
        name="approval-reject-then-blocked",
        definition=_APPROVAL,
        steps=[("reject", 0.0), ("approve", 0.0)],  # 2nd step from terminal
        expect_error=TransitionError,
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_machine_cases(case: Case) -> None:
    machine = StateMachine.from_dict(case.definition)
    pilot = Pilot(machine, **case.limits)

    if case.expect_error is not None:
        with pytest.raises(case.expect_error):
            for tool, cost in case.steps:
                pilot.step(tool, cost=cost)
    else:
        for tool, cost in case.steps:
            pilot.step(tool, cost=cost)
        assert pilot.state == case.expect_final_state
