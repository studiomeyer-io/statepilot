"""Tests for YAML loading of state machines.

These require the optional ``pyyaml`` dependency, which is part of the ``dev``
extra. If it is somehow missing the tests are skipped rather than failing.
"""

from __future__ import annotations

import pytest

from statepilot import Pilot, StateMachine, StateMachineError, TransitionError

pytest.importorskip("yaml")

YAML_DEF = """
initial: research
terminal:
  - published
transitions:
  - {from: research, to: research, tool: search}
  - {from: research, to: draft, tool: write_draft}
  - {from: draft, to: review, tool: review}
  - {from: review, to: published, tool: publish}
"""


def test_from_yaml_string_loads_and_enforces() -> None:
    machine = StateMachine.from_yaml(YAML_DEF)
    assert machine.initial == "research"
    assert machine.is_terminal("published")

    pilot = Pilot(machine)
    pilot.step("write_draft")
    pilot.step("review")
    pilot.step("publish")
    assert pilot.done is True

    # forbidden transition still enforced from a YAML-defined machine
    fresh = Pilot(machine)
    with pytest.raises(TransitionError):
        fresh.step("publish")


def test_from_yaml_file(tmp_path: object) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    path = tmp_path / "machine.yaml"
    path.write_text(YAML_DEF, encoding="utf-8")

    machine = StateMachine.from_yaml_file(str(path))
    assert machine.resolve("research", "write_draft") == "draft"


def test_from_yaml_round_trip() -> None:
    machine = StateMachine.from_yaml(YAML_DEF)
    rebuilt = StateMachine.from_dict(machine.to_dict())
    assert rebuilt.states == machine.states
    assert set(rebuilt.transitions) == set(machine.transitions)
    assert rebuilt.terminal == machine.terminal


def test_from_yaml_non_mapping_rejected() -> None:
    with pytest.raises(StateMachineError, match="Top-level YAML must be a mapping"):
        StateMachine.from_yaml("- just\n- a\n- list\n")


def test_from_yaml_invalid_syntax_rejected() -> None:
    with pytest.raises(StateMachineError, match="Could not parse YAML"):
        StateMachine.from_yaml("initial: research\n  bad: : indent")


def test_from_yaml_parses_string_never_reads_a_file(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: an inline string is always parsed as YAML content, never read
    as a file — even if a file of that name exists in the cwd. Closes the
    path-detection footgun where a malformed policy could be silently loaded."""
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    decoy = tmp_path / "x.yaml"
    decoy.write_text(YAML_DEF, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    # "x.yaml" parses as a scalar string (not a mapping) -> error. The old,
    # path-detecting behaviour would have read the decoy file and built a machine.
    with pytest.raises(StateMachineError, match="must be a mapping"):
        StateMachine.from_yaml("x.yaml")
