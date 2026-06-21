"""Adversarial / fail-closed hardening tests.

These guard against ways the runtime guards could be *bypassed* (fail open) by
malformed input. The central invariant: an invalid argument (non-finite cost or
budget) is a programming error that raises :class:`ValueError` — it must never be
treated as a silent guard decision that lets a step through.

Background: ``NaN`` defeats every numeric comparison (``NaN > x`` is always
``False``). Before these guards, a single ``NaN`` cost slipped past the budget
check *and* poisoned ``cost_spent`` to ``NaN``, permanently disabling the budget
guard for the rest of the run. A ``NaN``/``inf`` budget did the same from
construction. All of that now fails closed.
"""

from __future__ import annotations

import math

import pytest

from statepilot import (
    BudgetExceeded,
    Pilot,
    StateMachine,
    guarded,
)


@pytest.fixture
def loop_machine() -> StateMachine:
    """Single self-looping state — lets us hammer cost/budget guards."""
    return StateMachine.builder().initial("s").transition("s", "s", tool="tick").build()


# -- NaN / inf cost on step() (the budget-bypass + state-poison class) --------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_step_rejects_non_finite_cost(loop_machine: StateMachine, bad: float) -> None:
    pilot = Pilot(loop_machine, budget=1.0)
    with pytest.raises(ValueError, match="finite"):
        pilot.step("tick", cost=bad)
    # Fail-closed: the rejected step changed nothing; the guard is still alive.
    assert pilot.cost_spent == 0.0
    assert math.isfinite(pilot.cost_spent)
    assert pilot.steps_taken == 0


def test_nan_cost_does_not_poison_budget_guard(loop_machine: StateMachine) -> None:
    """Regression for the headline fail-open: a NaN cost must not slip through and
    leave the budget guard permanently dead (NaN > anything == False)."""
    pilot = Pilot(loop_machine, budget=1.0)
    with pytest.raises(ValueError):
        pilot.step("tick", cost=float("nan"))
    # The budget guard must still bite afterwards.
    pilot.step("tick", cost=1.0)  # exactly at budget, allowed
    with pytest.raises(BudgetExceeded):
        pilot.step("tick", cost=0.5)  # 1.5 > 1.0 -> still enforced


def test_inf_cost_rejected_even_without_budget(loop_machine: StateMachine) -> None:
    """Without a budget there is no BudgetExceeded to catch inf/NaN, so an
    unguarded inf cost would silently land in cost_spent/the trace. It must be
    rejected as an invalid argument regardless of whether a budget is set."""
    pilot = Pilot(loop_machine, budget=None)
    with pytest.raises(ValueError, match="finite"):
        pilot.step("tick", cost=float("inf"))
    assert pilot.cost_spent == 0.0


# -- NaN / inf cost on can() (planning path must agree with step()) -----------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_can_rejects_non_finite_cost(loop_machine: StateMachine, bad: float) -> None:
    pilot = Pilot(loop_machine, budget=1.0)
    with pytest.raises(ValueError, match="finite"):
        pilot.can("tick", cost=bad)


def test_can_nan_does_not_silently_allow(loop_machine: StateMachine) -> None:
    """can(cost=NaN) must not return True ("allowed") via a dead comparison."""
    pilot = Pilot(loop_machine, budget=1.0)
    with pytest.raises(ValueError):
        pilot.can("tick", cost=float("nan"))


# -- NaN / inf budget at construction (guard dead from the start) -------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_pilot_rejects_non_finite_budget(
    loop_machine: StateMachine, bad: float
) -> None:
    with pytest.raises(ValueError, match="finite"):
        Pilot(loop_machine, budget=bad)


def test_finite_budget_and_zero_cost_still_work(loop_machine: StateMachine) -> None:
    """Legitimate values keep working — the hardening only rejects non-finite."""
    pilot = Pilot(loop_machine, budget=2.0)
    pilot.step("tick", cost=0.0)
    pilot.step("tick", cost=2.0)  # exactly budget, allowed
    assert pilot.cost_spent == pytest.approx(2.0)
    with pytest.raises(BudgetExceeded):
        pilot.step("tick", cost=0.1)


def test_no_budget_allows_large_finite_cost(loop_machine: StateMachine) -> None:
    """budget=None genuinely disables the budget guard for finite costs."""
    pilot = Pilot(loop_machine, budget=None)
    pilot.step("tick", cost=1e9)
    assert pilot.cost_spent == pytest.approx(1e9)


# -- decorator inherits the hardening -----------------------------------------


def test_guarded_decorator_rejects_nan_cost_before_body(
    loop_machine: StateMachine,
) -> None:
    pilot = Pilot(loop_machine, budget=1.0)
    ran = False

    @guarded(pilot, tool="tick", cost=float("nan"))
    def work() -> None:
        nonlocal ran
        ran = True

    with pytest.raises(ValueError, match="finite"):
        work()
    assert ran is False  # body must not have executed
    assert pilot.cost_spent == 0.0


# -- exact tool matching: no aliasing / case / whitespace evasion -------------


def test_tool_matching_is_exact_no_evasion() -> None:
    """The order guard keys on the exact tool string. Case- and whitespace-
    variants of an allowed tool must NOT resolve (no accidental aliasing in
    either direction), so an attacker can't smuggle a forbidden call through a
    near-miss name."""
    machine = (
        StateMachine.builder()
        .initial("a")
        .transition("a", "b", tool="Search")
        .terminal("b")
        .build()
    )
    assert machine.resolve("a", "Search") == "b"  # the real one works
    assert machine.resolve("a", "search") is None  # different case -> blocked
    assert machine.resolve("a", " Search") is None  # leading space -> blocked
    assert machine.resolve("a", "Search ") is None  # trailing space -> blocked
    assert machine.resolve("a", "Search\t") is None  # tab -> blocked


def test_step_blocks_case_and_whitespace_variants() -> None:
    """End-to-end: a near-miss tool name raises rather than advancing state."""
    from statepilot import TransitionError

    machine = (
        StateMachine.builder()
        .initial("a")
        .transition("a", "b", tool="Search")
        .terminal("b")
        .build()
    )
    pilot = Pilot(machine)
    with pytest.raises(TransitionError):
        pilot.step("search")  # wrong case
    assert pilot.state == "a"
    with pytest.raises(TransitionError):
        pilot.step("Search ")  # trailing space
    assert pilot.state == "a"
    # the exact name does advance
    assert pilot.step("Search") == "b"
