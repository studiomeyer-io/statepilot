"""Tests for the experimental LangGraph adapter.

The adapter targets the stable LangGraph *node contract* (a callable
``state -> partial_state_dict``) and never imports ``langgraph`` itself, so these
tests exercise it with plain dict-returning callables — exactly the shape
LangGraph nodes have — without needing LangGraph installed.
"""

from __future__ import annotations

from typing import Any

import pytest

from statepilot import Pilot, StateMachine, TransitionError
from statepilot.adapters import guard_node


@pytest.fixture
def pilot(publish_machine: StateMachine) -> Pilot:
    return Pilot(publish_machine, budget=5.0)


def test_guard_node_runs_node_when_allowed(pilot: Pilot) -> None:
    def write_draft(state: dict[str, Any]) -> dict[str, Any]:
        return {"draft": "hello " + state.get("topic", "")}

    guarded_node = guard_node(pilot, write_draft, tool="write_draft", cost=1.0)
    result = guarded_node({"topic": "agents"})

    assert result == {"draft": "hello agents"}
    assert pilot.state == "draft"
    assert pilot.cost_spent == pytest.approx(1.0)


def test_guard_node_defaults_tool_to_node_name(pilot: Pilot) -> None:
    def search(state: dict[str, Any]) -> dict[str, Any]:
        return {"hits": 3}

    guarded_node = guard_node(pilot, search)
    guarded_node({})
    assert pilot.history[0].tool == "search"


def test_guard_node_blocks_node_on_violation(pilot: Pilot) -> None:
    ran = False

    def publish(state: dict[str, Any]) -> dict[str, Any]:
        nonlocal ran
        ran = True
        return {"url": "x"}

    guarded_node = guard_node(pilot, publish, tool="publish")
    with pytest.raises(TransitionError):
        guarded_node({})  # publish forbidden from research
    assert ran is False
    assert pilot.state == "research"


def test_guard_node_preserves_node_name(pilot: Pilot) -> None:
    def my_node(state: dict[str, Any]) -> dict[str, Any]:
        return {}

    wrapped = guard_node(pilot, my_node, tool="search")
    assert wrapped.__name__ == "my_node"
