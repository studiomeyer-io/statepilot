"""Tests for the :func:`guarded` decorator."""

from __future__ import annotations

import pytest

from statepilot import (
    BudgetExceeded,
    Pilot,
    StateMachine,
    TransitionError,
    guarded,
)


@pytest.fixture
def pilot(publish_machine: StateMachine) -> Pilot:
    return Pilot(publish_machine, budget=5.0)


def test_guarded_uses_func_name_as_tool(pilot: Pilot) -> None:
    calls: list[str] = []

    @guarded(pilot)
    def search(query: str) -> str:
        calls.append(query)
        return f"results for {query}"

    assert search("agents") == "results for agents"
    assert calls == ["agents"]
    assert pilot.state == "research"
    assert pilot.steps_taken == 1
    assert pilot.history[0].tool == "search"


def test_guarded_explicit_tool_name(pilot: Pilot) -> None:
    @guarded(pilot, tool="write_draft")
    def make_the_draft() -> str:
        return "draft body"

    assert make_the_draft() == "draft body"
    assert pilot.state == "draft"
    assert pilot.history[0].tool == "write_draft"


def test_guarded_blocks_body_on_violation(pilot: Pilot) -> None:
    ran = False

    @guarded(pilot, tool="publish")
    def publish() -> None:
        nonlocal ran
        ran = True

    with pytest.raises(TransitionError):
        publish()  # publish not allowed from research
    assert ran is False  # body must not have executed
    assert pilot.state == "research"


def test_guarded_charges_cost(pilot: Pilot) -> None:
    @guarded(pilot, cost=2.0)
    def search() -> None:
        return None

    search()
    assert pilot.cost_spent == pytest.approx(2.0)


def test_guarded_budget_blocks_body() -> None:
    machine = (
        StateMachine.builder().initial("s").transition("s", "s", tool="work").build()
    )
    pilot = Pilot(machine, budget=1.0)
    runs: list[int] = []

    @guarded(pilot, tool="work", cost=0.6)
    def work() -> None:
        runs.append(1)

    work()  # 0.6 spent
    with pytest.raises(BudgetExceeded):
        work()  # 0.6 + 0.6 > 1.0 -> blocked before body
    assert runs == [1]


def test_guarded_preserves_metadata(pilot: Pilot) -> None:
    @guarded(pilot, tool="search")
    def my_tool(x: int) -> int:
        """Docstring stays."""
        return x

    assert my_tool.__name__ == "my_tool"
    assert my_tool.__doc__ == "Docstring stays."
