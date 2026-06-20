"""The :func:`guarded` decorator.

Wrap a tool function so that a :class:`statepilot.pilot.Pilot` validates the call
*before* the wrapped function runs. If the pilot rejects the call, the function
body never executes and the guard exception propagates.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from .pilot import Pilot

__all__ = ["guarded"]

F = TypeVar("F", bound="Callable[..., Any]")


def guarded(
    pilot: Pilot,
    *,
    tool: str | None = None,
    cost: float = 0.0,
) -> Callable[[F], F]:
    """Decorate a tool function with a state-machine guard.

    Args:
        pilot: The :class:`~statepilot.pilot.Pilot` that enforces the rules.
        tool: The tool name used for the transition. Defaults to the wrapped
            function's ``__name__``.
        cost: Cost to attribute to the call (counts against the pilot budget).

    The decorated function calls :meth:`Pilot.step` with the resolved tool name
    and cost *before* executing its body. A
    :class:`~statepilot.exceptions.GuardViolation` therefore prevents the body
    from running at all.

    Example::

        pilot = Pilot(machine, budget=5.0)

        @guarded(pilot, cost=1.0)
        def research(query: str) -> str:
            return do_research(query)

        research("agents")  # advances the machine, charges 1.0, then runs
    """

    def decorate(func: F) -> F:
        tool_name = tool if tool is not None else func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            pilot.step(tool_name, cost=cost)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorate
