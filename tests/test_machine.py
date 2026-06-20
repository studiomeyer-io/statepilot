"""Tests for the :class:`StateMachine` definition and builder."""

from __future__ import annotations

import pytest

from statepilot import StateMachine, StateMachineError, Transition


def test_builder_builds_valid_machine(publish_machine: StateMachine) -> None:
    assert publish_machine.initial == "research"
    assert "published" in publish_machine.states
    assert publish_machine.is_terminal("published")
    assert not publish_machine.is_terminal("research")


def test_allowed_tools_sorted(publish_machine: StateMachine) -> None:
    assert publish_machine.allowed_tools("research") == ("search", "write_draft")
    assert publish_machine.allowed_tools("review") == ("publish", "revise")
    assert publish_machine.allowed_tools("published") == ()


def test_resolve_returns_dest_or_none(publish_machine: StateMachine) -> None:
    assert publish_machine.resolve("research", "write_draft") == "draft"
    assert publish_machine.resolve("research", "nope") is None


def test_builder_requires_initial() -> None:
    builder = StateMachine.builder().transition("a", "b", tool="go")
    with pytest.raises(StateMachineError, match="No initial state"):
        builder.build()


def test_terminal_state_cannot_have_outgoing_transition() -> None:
    builder = (
        StateMachine.builder()
        .initial("a")
        .transition("a", "b", tool="go")
        .transition("b", "a", tool="back")
        .terminal("b")
    )
    with pytest.raises(StateMachineError, match="Terminal state 'b' cannot"):
        builder.build()


def test_ambiguous_transition_rejected() -> None:
    builder = (
        StateMachine.builder()
        .initial("a")
        .transition("a", "b", tool="go")
        .transition("a", "c", tool="go")
    )
    with pytest.raises(StateMachineError, match="Ambiguous transition"):
        builder.build()


def test_initial_must_be_a_state() -> None:
    with pytest.raises(StateMachineError, match="Initial state"):
        StateMachine(
            states=frozenset({"a"}),
            initial="missing",
            transitions=(),
        )


def test_empty_states_rejected() -> None:
    with pytest.raises(StateMachineError, match="at least one state"):
        StateMachine(states=frozenset(), initial="a", transitions=())


def test_transition_dest_must_be_known_state() -> None:
    with pytest.raises(StateMachineError, match="dest 'c' is not"):
        StateMachine(
            states=frozenset({"a", "b"}),
            initial="a",
            transitions=(Transition("a", "c", "go"),),
        )


def test_allowed_tools_unknown_state_raises(publish_machine: StateMachine) -> None:
    with pytest.raises(StateMachineError, match="Unknown state"):
        publish_machine.allowed_tools("nonexistent")


def test_from_dict_infers_states() -> None:
    machine = StateMachine.from_dict(
        {
            "initial": "idle",
            "terminal": ["done"],
            "transitions": [
                {"from": "idle", "to": "running", "tool": "start"},
                {"from": "running", "to": "done", "tool": "finish"},
            ],
        }
    )
    assert machine.states == frozenset({"idle", "running", "done"})
    assert machine.is_terminal("done")
    assert machine.resolve("idle", "start") == "running"


def test_from_dict_explicit_states_must_cover_all() -> None:
    with pytest.raises(StateMachineError, match="referenced but not declared"):
        StateMachine.from_dict(
            {
                "initial": "idle",
                "states": ["idle"],  # 'running' missing on purpose
                "transitions": [
                    {"from": "idle", "to": "running", "tool": "start"},
                ],
            }
        )


def test_from_dict_event_alias_for_tool() -> None:
    machine = StateMachine.from_dict(
        {
            "initial": "a",
            "transitions": [{"from": "a", "to": "b", "event": "go"}],
        }
    )
    assert machine.resolve("a", "go") == "b"


def test_from_dict_rejects_non_mapping() -> None:
    with pytest.raises(StateMachineError, match="must be a mapping"):
        StateMachine.from_dict([])  # type: ignore[arg-type]


def test_from_dict_requires_initial() -> None:
    with pytest.raises(StateMachineError, match="non-empty 'initial'"):
        StateMachine.from_dict({"transitions": []})


def test_to_dict_round_trip(publish_machine: StateMachine) -> None:
    data = publish_machine.to_dict()
    rebuilt = StateMachine.from_dict(data)
    assert rebuilt.states == publish_machine.states
    assert rebuilt.initial == publish_machine.initial
    assert rebuilt.terminal == publish_machine.terminal
    # transitions match as a set (order-independent)
    assert set(rebuilt.transitions) == set(publish_machine.transitions)


def test_builder_state_method_registers_states() -> None:
    machine = (
        StateMachine.builder()
        .initial("a")
        .state("a", "b", "c")  # pre-register, incl. an otherwise-orphan "c"
        .transition("a", "b", tool="go")
        .build()
    )
    assert machine.states == frozenset({"a", "b", "c"})


def test_from_dict_explicit_states_happy_path() -> None:
    machine = StateMachine.from_dict(
        {
            "initial": "idle",
            "states": ["idle", "running", "done"],
            "terminal": ["done"],
            "transitions": [
                {"from": "idle", "to": "running", "tool": "start"},
                {"from": "running", "to": "done", "tool": "finish"},
            ],
        }
    )
    assert machine.states == frozenset({"idle", "running", "done"})
    assert machine.resolve("running", "finish") == "done"


def test_from_dict_rejects_bad_states_type() -> None:
    with pytest.raises(StateMachineError, match="'states' must be a list"):
        StateMachine.from_dict(
            {
                "initial": "a",
                "states": "not-a-list",
                "transitions": [],
            }
        )


def test_from_dict_rejects_bad_terminal_type() -> None:
    with pytest.raises(StateMachineError, match="'terminal' must be a list"):
        StateMachine.from_dict(
            {
                "initial": "a",
                "terminal": "done",
                "transitions": [],
            }
        )


def test_from_dict_rejects_bad_transitions_type() -> None:
    with pytest.raises(StateMachineError, match="'transitions' must be a list"):
        StateMachine.from_dict({"initial": "a", "transitions": "nope"})


def test_from_dict_rejects_non_mapping_transition() -> None:
    with pytest.raises(StateMachineError, match="Transition #0 must be a mapping"):
        StateMachine.from_dict({"initial": "a", "transitions": ["bad"]})


def test_from_dict_rejects_transition_missing_field() -> None:
    with pytest.raises(StateMachineError, match="missing a valid 'to'"):
        StateMachine.from_dict(
            {"initial": "a", "transitions": [{"from": "a", "tool": "go"}]}
        )


def test_transition_source_must_be_known_state() -> None:
    with pytest.raises(StateMachineError, match="source 'x' is not"):
        StateMachine(
            states=frozenset({"a", "b"}),
            initial="a",
            transitions=(Transition("x", "b", "go"),),
        )


def test_terminal_must_be_a_state_constructor() -> None:
    with pytest.raises(StateMachineError, match="Terminal state 'z' is not"):
        StateMachine(
            states=frozenset({"a"}),
            initial="a",
            transitions=(),
            terminal=frozenset({"z"}),
        )


def test_builder_accepts_initial_arg() -> None:
    machine = (
        StateMachine.builder("start")  # initial passed to builder() directly
        .transition("start", "end", tool="go")
        .terminal("end")
        .build()
    )
    assert machine.initial == "start"
    assert machine.resolve("start", "go") == "end"
