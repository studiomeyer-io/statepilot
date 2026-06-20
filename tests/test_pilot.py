"""Tests for the runtime guard :class:`Pilot`."""

from __future__ import annotations

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


def test_happy_path_full_sequence(publish_machine: StateMachine) -> None:
    pilot = Pilot(publish_machine)
    assert pilot.state == "research"
    assert pilot.step("search") == "research"
    assert pilot.step("write_draft") == "draft"
    assert pilot.step("review") == "review"
    assert pilot.step("publish") == "published"
    assert pilot.done is True
    assert pilot.steps_taken == 4
    tools = [record.tool for record in pilot.history]
    assert tools == ["search", "write_draft", "review", "publish"]


def test_forbidden_transition_raises(publish_machine: StateMachine) -> None:
    pilot = Pilot(publish_machine)
    with pytest.raises(TransitionError) as exc:
        pilot.step("publish")  # cannot publish straight from research
    assert exc.value.tool == "publish"
    assert exc.value.state == "research"
    assert "write_draft" in exc.value.allowed
    # state unchanged after a violation
    assert pilot.state == "research"
    assert pilot.steps_taken == 0


def test_transition_error_is_guard_violation(publish_machine: StateMachine) -> None:
    pilot = Pilot(publish_machine)
    with pytest.raises(GuardViolation):
        pilot.step("publish")


def test_terminal_state_blocks_further_steps(linear_machine: StateMachine) -> None:
    pilot = Pilot(linear_machine)
    pilot.step("go")
    assert pilot.done is True
    with pytest.raises(TransitionError, match="not allowed in state 'b'"):
        pilot.step("go")
    assert pilot.allowed_tools() == ()


def test_loop_limit_on_state_visits(publish_machine: StateMachine) -> None:
    # research counts as visit 1; each "search" re-enters research.
    pilot = Pilot(publish_machine, max_state_visits=3)
    pilot.step("search")  # visit 2
    pilot.step("search")  # visit 3
    with pytest.raises(LoopLimitExceeded) as exc:
        pilot.step("search")  # would be visit 4
    assert exc.value.kind == "state"
    assert exc.value.name == "research"
    assert exc.value.limit == 3
    assert pilot.state == "research"


def test_loop_limit_on_consecutive_tool() -> None:
    machine = (
        StateMachine.builder()
        .initial("s")
        .transition("s", "s", tool="ping")
        .transition("s", "done", tool="stop")
        .terminal("done")
        .build()
    )
    pilot = Pilot(machine, max_consecutive_tool=2)
    pilot.step("ping")
    pilot.step("ping")
    with pytest.raises(LoopLimitExceeded) as exc:
        pilot.step("ping")
    assert exc.value.kind == "tool"
    assert exc.value.name == "ping"


def test_consecutive_tool_counter_resets_on_different_tool() -> None:
    machine = (
        StateMachine.builder()
        .initial("s")
        .transition("s", "s", tool="ping")
        .transition("s", "t", tool="hop")
        .transition("t", "s", tool="back")
        .build()
    )
    pilot = Pilot(machine, max_consecutive_tool=2)
    pilot.step("ping")
    pilot.step("hop")  # resets consecutive counter
    pilot.step("back")
    pilot.step("ping")  # consecutive ping count is 1 again
    assert pilot.state == "s"


def test_budget_exceeded(publish_machine: StateMachine) -> None:
    pilot = Pilot(publish_machine, budget=1.5)
    pilot.step("search", cost=1.0)
    with pytest.raises(BudgetExceeded) as exc:
        pilot.step("search", cost=1.0)  # 1.0 + 1.0 > 1.5
    assert exc.value.budget == 1.5
    assert pilot.cost_spent == pytest.approx(1.0)


def test_budget_exact_boundary_allowed(publish_machine: StateMachine) -> None:
    pilot = Pilot(publish_machine, budget=2.0)
    pilot.step("search", cost=1.0)
    pilot.step("search", cost=1.0)  # exactly 2.0, allowed
    assert pilot.cost_spent == pytest.approx(2.0)


def test_budget_float_accumulation_does_not_misfire() -> None:
    machine = (
        StateMachine.builder().initial("s").transition("s", "s", tool="tick").build()
    )
    pilot = Pilot(machine, budget=1.0)
    for _ in range(10):
        pilot.step("tick", cost=0.1)  # 0.1 * 10 == 1.0 in exact terms
    assert pilot.cost_spent == pytest.approx(1.0)


def test_step_limit_exceeded(publish_machine: StateMachine) -> None:
    pilot = Pilot(publish_machine, max_steps=2)
    pilot.step("search")
    pilot.step("search")
    with pytest.raises(StepLimitExceeded) as exc:
        pilot.step("search")
    assert exc.value.limit == 2
    assert pilot.steps_taken == 2


def test_can_predicts_step_without_mutation(publish_machine: StateMachine) -> None:
    pilot = Pilot(publish_machine, budget=1.0)
    assert pilot.can("write_draft") is True
    assert pilot.can("publish") is False  # not allowed from research
    assert pilot.can("search", cost=2.0) is False  # over budget
    # can() did not change anything
    assert pilot.state == "research"
    assert pilot.steps_taken == 0


def test_can_false_in_terminal(linear_machine: StateMachine) -> None:
    pilot = Pilot(linear_machine)
    pilot.step("go")
    assert pilot.can("go") is False


def test_negative_cost_rejected(publish_machine: StateMachine) -> None:
    pilot = Pilot(publish_machine)
    with pytest.raises(ValueError, match="cost must be"):
        pilot.step("search", cost=-1.0)


def test_invalid_config_rejected(publish_machine: StateMachine) -> None:
    with pytest.raises(ValueError, match="budget"):
        Pilot(publish_machine, budget=-1.0)
    with pytest.raises(ValueError, match="max_steps"):
        Pilot(publish_machine, max_steps=-1)
    with pytest.raises(ValueError, match="max_state_visits"):
        Pilot(publish_machine, max_state_visits=0)
    with pytest.raises(ValueError, match="max_consecutive_tool"):
        Pilot(publish_machine, max_consecutive_tool=0)


def test_to_trace_shape(publish_machine: StateMachine) -> None:
    pilot = Pilot(publish_machine, budget=5.0, max_steps=10, max_state_visits=3)
    pilot.step("search", cost=0.5)
    pilot.step("write_draft", cost=1.0)
    trace = pilot.to_trace()

    assert trace["initial"] == "research"
    assert trace["state"] == "draft"
    assert trace["done"] is False
    assert trace["steps_taken"] == 2
    assert trace["cost_spent"] == pytest.approx(1.5)
    assert trace["budget"] == 5.0
    assert trace["limits"] == {
        "max_steps": 10,
        "max_state_visits": 3,
        "max_consecutive_tool": None,
    }
    assert isinstance(trace["history"], list)
    assert len(trace["history"]) == 2

    first = trace["history"][0]
    assert set(first.keys()) == {
        "index",
        "tool",
        "source",
        "dest",
        "cost",
        "cumulative_cost",
        "timestamp",
    }
    assert first["tool"] == "search"
    assert first["source"] == "research"
    assert first["dest"] == "research"
    assert first["cumulative_cost"] == pytest.approx(0.5)
    assert trace["history"][1]["cumulative_cost"] == pytest.approx(1.5)


def test_to_trace_is_json_serialisable(publish_machine: StateMachine) -> None:
    import json

    pilot = Pilot(publish_machine, budget=5.0)
    pilot.step("search", cost=0.5)
    # Must not raise.
    dumped = json.dumps(pilot.to_trace())
    assert "research" in dumped


def test_reset_clears_state(publish_machine: StateMachine) -> None:
    pilot = Pilot(publish_machine, budget=5.0)
    pilot.step("search", cost=1.0)
    pilot.step("write_draft", cost=1.0)
    assert pilot.state == "draft"

    pilot.reset()
    assert pilot.state == "research"
    assert pilot.cost_spent == 0.0
    assert pilot.history == ()
    # Loop counter for initial state reset, so the machine is fully reusable.
    pilot.step("search")
    assert pilot.state == "research"


def test_revise_sends_back_to_draft(publish_machine: StateMachine) -> None:
    pilot = Pilot(publish_machine)
    pilot.step("write_draft")
    pilot.step("review")
    assert pilot.step("revise") == "draft"
    assert pilot.step("review") == "review"
    assert pilot.step("publish") == "published"


def test_can_false_when_step_limit_reached() -> None:
    machine = (
        StateMachine.builder().initial("s").transition("s", "s", tool="tick").build()
    )
    pilot = Pilot(machine, max_steps=1)
    pilot.step("tick")
    assert pilot.can("tick") is False  # step limit branch


def test_can_false_on_consecutive_tool_limit() -> None:
    machine = (
        StateMachine.builder().initial("s").transition("s", "s", tool="ping").build()
    )
    pilot = Pilot(machine, max_consecutive_tool=1)
    pilot.step("ping")
    assert pilot.can("ping") is False  # consecutive-tool branch


def test_can_false_on_state_visit_limit() -> None:
    machine = (
        StateMachine.builder().initial("s").transition("s", "s", tool="loop").build()
    )
    # initial visit counts as 1; with limit 1 any re-entry is disallowed.
    pilot = Pilot(machine, max_state_visits=1)
    assert pilot.can("loop") is False  # state-visit branch


def test_can_rejects_negative_cost_like_step(publish_machine: StateMachine) -> None:
    """Regression: can() and step() agree on invalid input — a negative cost is a
    programming error (ValueError) in both, not a silent guard decision."""
    pilot = Pilot(publish_machine)
    with pytest.raises(ValueError):
        pilot.can("search", cost=-1.0)
    with pytest.raises(ValueError):
        pilot.step("search", cost=-1.0)


def test_history_is_immutable_snapshot(publish_machine: StateMachine) -> None:
    """Regression: history is a tuple snapshot, so external code cannot desync the
    run's step counter by mutating the returned list."""
    pilot = Pilot(publish_machine)
    pilot.step("search")
    snapshot = pilot.history
    assert isinstance(snapshot, tuple)
    assert len(snapshot) == 1
    assert pilot.steps_taken == 1
