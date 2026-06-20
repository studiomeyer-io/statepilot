"""LangGraph adapter — **experimental**.

LangGraph's public surface (``StateGraph``, ``add_node``, ``ToolNode``) has moved
across releases, but one contract has been stable since early versions: a *node*
is a callable that takes the graph state and returns a partial-state ``dict``::

    def my_node(state: dict) -> dict:
        ...
        return {"some_key": value}

This adapter hooks into that contract. :func:`guard_node` wraps any node callable
so that a :class:`statepilot.pilot.Pilot` validates the transition *before* the
node body runs. Because it targets the callable contract and never imports
``langgraph``, it does not break when the LangGraph API churns, and it adds no
import-time dependency.

It is deliberately minimal. For anything beyond "guard this node", drive the
:class:`~statepilot.pilot.Pilot` yourself inside your node functions — that is the
fully supported path. Treat this module as a convenience, not a framework
integration layer.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from statepilot.pilot import Pilot

__all__ = ["guard_node"]


def guard_node(
    pilot: Pilot,
    node: Callable[[Any], Any],
    *,
    tool: str | None = None,
    cost: float = 0.0,
) -> Callable[[Any], Any]:
    """Wrap a LangGraph node callable with a statepilot guard.

    Args:
        pilot: The :class:`~statepilot.pilot.Pilot` enforcing the rules.
        node: A LangGraph node — any callable ``state -> partial_state_dict``.
        tool: Tool name used for the transition. Defaults to the node's
            ``__name__`` (or ``"node"`` for objects without one).
        cost: Cost to attribute to entering this node.

    Returns:
        A callable with the same ``state -> result`` signature as ``node``. It
        calls :meth:`Pilot.step` before invoking ``node``; a
        :class:`~statepilot.exceptions.GuardViolation` therefore stops the node
        from running.

    Example (pseudocode — requires ``langgraph`` installed at call time)::

        from langgraph.graph import StateGraph
        from statepilot import StateMachine, Pilot
        from statepilot.adapters import guard_node

        pilot = Pilot(machine, budget=5.0)
        graph = StateGraph(MyState)
        graph.add_node("research", guard_node(pilot, research_node, cost=1.0))
        graph.add_node("draft", guard_node(pilot, draft_node))

    .. warning::
        Experimental. The contract it relies on (node = callable returning a
        partial-state dict) is stable, but conditional edges, ``Send`` fan-out
        and checkpoint/resume are out of scope and untested here.
    """
    tool_name = tool if tool is not None else getattr(node, "__name__", "node")

    @functools.wraps(node)
    def wrapped(state: Any) -> Any:
        pilot.step(tool_name, cost=cost)
        return node(state)

    return wrapped
