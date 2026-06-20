"""The :class:`StateMachine` definition and its builder.

A :class:`StateMachine` is an immutable, validated description of:

* the set of valid states,
* the initial state,
* which states are terminal (no outgoing transitions allowed), and
* the transitions, each bound to a *tool* (or generic event) name.

It carries no runtime state. Apply it to a :class:`statepilot.pilot.Pilot` to
enforce it at runtime. Build one with the fluent builder, :meth:`from_dict`, or
:meth:`from_yaml`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .exceptions import StateMachineError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from os import PathLike

__all__ = ["StateMachine", "StateMachineBuilder", "Transition"]


@dataclass(frozen=True, slots=True)
class Transition:
    """A single edge in the state machine.

    Attributes:
        source: State the transition starts from.
        dest: State the transition leads to.
        tool: Name of the tool/event that triggers this transition.
    """

    source: str
    dest: str
    tool: str


@dataclass(frozen=True, slots=True)
class StateMachine:
    """An immutable, validated state machine definition.

    Prefer the constructors (:meth:`builder`, :meth:`from_dict`,
    :meth:`from_yaml`) over instantiating this class directly — they validate
    inputs and produce the internal lookup index.
    """

    states: frozenset[str]
    initial: str
    transitions: tuple[Transition, ...]
    terminal: frozenset[str] = field(default_factory=frozenset)
    # Index: (source_state, tool) -> dest_state. Built in __post_init__.
    _index: dict[tuple[str, str], str] = field(
        default_factory=dict, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        if not self.states:
            raise StateMachineError("A state machine needs at least one state.")
        if self.initial not in self.states:
            raise StateMachineError(
                f"Initial state '{self.initial}' is not in the set of states."
            )
        for bad in self.terminal - self.states:
            raise StateMachineError(
                f"Terminal state '{bad}' is not in the set of states."
            )

        index: dict[tuple[str, str], str] = {}
        for tr in self.transitions:
            if tr.source not in self.states:
                raise StateMachineError(
                    f"Transition source '{tr.source}' is not a known state."
                )
            if tr.dest not in self.states:
                raise StateMachineError(
                    f"Transition dest '{tr.dest}' is not a known state."
                )
            if tr.source in self.terminal:
                raise StateMachineError(
                    f"Terminal state '{tr.source}' cannot have outgoing "
                    f"transitions (tool '{tr.tool}')."
                )
            key = (tr.source, tr.tool)
            if key in index:
                raise StateMachineError(
                    f"Ambiguous transition: tool '{tr.tool}' is defined more "
                    f"than once for state '{tr.source}'."
                )
            index[key] = tr.dest
        # frozen dataclass: bypass the frozen setter for the cached index.
        object.__setattr__(self, "_index", index)

    # -- queries ----------------------------------------------------------

    def is_terminal(self, state: str) -> bool:
        """Return ``True`` if ``state`` is a terminal state."""
        return state in self.terminal

    def allowed_tools(self, state: str) -> tuple[str, ...]:
        """Return the tools allowed from ``state``, sorted for determinism."""
        if state not in self.states:
            raise StateMachineError(f"Unknown state '{state}'.")
        return tuple(sorted(tool for (src, tool) in self._index if src == state))

    def resolve(self, state: str, tool: str) -> str | None:
        """Return the destination state for ``(state, tool)``.

        Returns ``None`` when the transition is not allowed. Does not raise; the
        :class:`statepilot.pilot.Pilot` decides how to react to ``None``.
        """
        return self._index.get((state, tool))

    # -- constructors -----------------------------------------------------

    @classmethod
    def builder(cls, initial: str | None = None) -> StateMachineBuilder:
        """Return a fresh fluent :class:`StateMachineBuilder`."""
        builder = StateMachineBuilder()
        if initial is not None:
            builder.initial(initial)
        return builder

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StateMachine:
        """Build a state machine from a plain mapping.

        Expected shape::

            {
              "initial": "idle",
              "states": ["idle", "running", "done"],   # optional, inferred otherwise
              "terminal": ["done"],                      # optional
              "transitions": [
                {"from": "idle", "to": "running", "tool": "start"},
                {"from": "running", "to": "done", "tool": "finish"},
              ],
            }

        ``states`` may be omitted; it is then inferred from ``initial`` plus
        every state mentioned in ``transitions`` and ``terminal``.
        """
        if not isinstance(data, dict):
            raise StateMachineError("State machine definition must be a mapping.")

        initial = data.get("initial")
        if not isinstance(initial, str) or not initial:
            raise StateMachineError(
                "State machine definition needs a non-empty 'initial' state."
            )

        raw_transitions = data.get("transitions", [])
        if not isinstance(raw_transitions, list):
            raise StateMachineError("'transitions' must be a list.")

        transitions: list[Transition] = []
        mentioned: set[str] = {initial}
        for i, raw in enumerate(raw_transitions):
            if not isinstance(raw, dict):
                raise StateMachineError(f"Transition #{i} must be a mapping.")
            source = raw.get("from")
            dest = raw.get("to")
            tool = raw.get("tool", raw.get("event"))
            for label, value in (("from", source), ("to", dest), ("tool", tool)):
                if not isinstance(value, str) or not value:
                    raise StateMachineError(
                        f"Transition #{i} is missing a valid '{label}'."
                    )
            assert isinstance(source, str)
            assert isinstance(dest, str)
            assert isinstance(tool, str)
            transitions.append(Transition(source=source, dest=dest, tool=tool))
            mentioned.update((source, dest))

        terminal_raw = data.get("terminal", [])
        if not isinstance(terminal_raw, list) or not all(
            isinstance(s, str) for s in terminal_raw
        ):
            raise StateMachineError("'terminal' must be a list of strings.")
        terminal: set[str] = set(terminal_raw)
        mentioned.update(terminal)

        states_raw = data.get("states")
        if states_raw is None:
            states = mentioned
        else:
            if not isinstance(states_raw, list) or not all(
                isinstance(s, str) for s in states_raw
            ):
                raise StateMachineError("'states' must be a list of strings.")
            states = set(states_raw)
            missing = mentioned - states
            if missing:
                raise StateMachineError(
                    "States referenced but not declared in 'states': "
                    + ", ".join(sorted(missing))
                )

        return cls(
            states=frozenset(states),
            initial=initial,
            transitions=tuple(transitions),
            terminal=frozenset(terminal),
        )

    @classmethod
    def from_yaml(cls, text: str) -> StateMachine:
        """Build a state machine from an inline YAML **string**.

        Requires the optional ``pyyaml`` dependency — install with
        ``pip install statepilot[yaml]``. This method never touches the
        filesystem, so an inline string is never accidentally interpreted as a
        path; to load a file use :meth:`from_yaml_file`.
        """
        try:
            import yaml
        except ModuleNotFoundError as exc:  # pragma: no cover - import guard
            raise StateMachineError(
                "from_yaml requires the optional 'pyyaml' dependency. "
                "Install it with: pip install statepilot[yaml]"
            ) from exc

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise StateMachineError(f"Could not parse YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise StateMachineError(
                "Top-level YAML must be a mapping with 'initial' and "
                "'transitions' keys."
            )
        return cls.from_dict(data)

    @classmethod
    def from_yaml_file(cls, path: str | PathLike[str]) -> StateMachine:
        """Build a state machine by reading the YAML **file** at ``path``.

        Requires the optional ``pyyaml`` dependency. Use :meth:`from_yaml` for an
        inline YAML string.
        """
        from pathlib import Path

        return cls.from_yaml(Path(path).read_text(encoding="utf-8"))

    def to_dict(self) -> dict[str, Any]:
        """Serialise back to a plain dict (round-trips with :meth:`from_dict`)."""
        return {
            "initial": self.initial,
            "states": sorted(self.states),
            "terminal": sorted(self.terminal),
            "transitions": [
                {"from": tr.source, "to": tr.dest, "tool": tr.tool}
                for tr in self.transitions
            ],
        }


class StateMachineBuilder:
    """Fluent builder for :class:`StateMachine`.

    Example::

        sm = (
            StateMachine.builder()
            .initial("idle")
            .transition("idle", "running", tool="start")
            .transition("running", "done", tool="finish")
            .terminal("done")
            .build()
        )

    Every mutating method returns ``self`` so calls can be chained.
    """

    def __init__(self) -> None:
        self._initial: str | None = None
        self._states: set[str] = set()
        self._terminal: set[str] = set()
        self._transitions: list[Transition] = []

    def initial(self, state: str) -> StateMachineBuilder:
        """Set the initial state (also registers it as a known state)."""
        self._initial = state
        self._states.add(state)
        return self

    def state(self, *states: str) -> StateMachineBuilder:
        """Explicitly register one or more states (usually optional)."""
        self._states.update(states)
        return self

    def transition(self, source: str, dest: str, *, tool: str) -> StateMachineBuilder:
        """Add a transition ``source --tool--> dest``.

        States are auto-registered. The keyword-only ``tool`` argument makes the
        binding explicit at the call site.
        """
        self._states.update((source, dest))
        self._transitions.append(Transition(source=source, dest=dest, tool=tool))
        return self

    def terminal(self, *states: str) -> StateMachineBuilder:
        """Mark one or more states as terminal."""
        self._states.update(states)
        self._terminal.update(states)
        return self

    def build(self) -> StateMachine:
        """Validate and return the immutable :class:`StateMachine`."""
        if self._initial is None:
            raise StateMachineError(
                "No initial state set. Call .initial(state) before .build()."
            )
        return StateMachine(
            states=frozenset(self._states),
            initial=self._initial,
            transitions=tuple(self._transitions),
            terminal=frozenset(self._terminal),
        )
