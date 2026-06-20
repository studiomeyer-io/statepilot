"""Runnable statepilot example: a guarded research/draft/review/publish pipeline.

Run it with::

    python examples/research_pipeline.py

It demonstrates, against a single state machine:

* the happy path running cleanly to a terminal state,
* a forbidden transition (publish before review) being rejected,
* the loop limit tripping on too many research iterations, and
* the budget cap stopping an over-spending run.

The "agent" here is just hand-written calls — statepilot does not call any LLM.
In a real agent you would let the model decide which guarded tool to call next;
statepilot makes the illegal choices impossible.
"""

from __future__ import annotations

from statepilot import (
    BudgetExceeded,
    LoopLimitExceeded,
    Pilot,
    StateMachine,
    TransitionError,
    guarded,
)


def build_machine() -> StateMachine:
    """research -> draft -> review -> published, with research looping + revise."""
    return (
        StateMachine.builder()
        .initial("research")
        .transition("research", "research", tool="search")
        .transition("research", "draft", tool="write_draft")
        .transition("draft", "review", tool="review")
        .transition("review", "draft", tool="revise")
        .transition("review", "published", tool="publish")
        .terminal("published")
        .build()
    )


def demo_happy_path() -> None:
    print("\n=== happy path ===")
    machine = build_machine()
    # initial visit counts as 1, so max_state_visits=4 allows 3 extra search loops
    pilot = Pilot(machine, budget=5.0, max_state_visits=4, max_steps=25)

    @guarded(pilot, cost=0.8)
    def search(query: str) -> str:
        return f"notes about {query}"

    @guarded(pilot, cost=1.2)
    def write_draft(notes: str) -> str:
        return f"draft based on: {notes}"

    @guarded(pilot)
    def review(draft: str) -> bool:
        return True

    @guarded(pilot, cost=0.3)
    def publish(draft: str) -> str:
        return "https://example.com/post"

    notes = search("deterministic agent guards")
    notes = search("state machines")  # second research loop
    draft = write_draft(notes)
    review(draft)
    url = publish(draft)

    print(f"published at: {url}")
    print(f"final state:  {pilot.state} (done={pilot.done})")
    print(f"steps:        {pilot.steps_taken}, cost: {pilot.cost_spent:.2f}")
    print("history:")
    for record in pilot.history:
        print(
            f"  {record.index}: {record.source:>9} --{record.tool}--> "
            f"{record.dest:<9} (cost {record.cost})"
        )


def demo_forbidden_transition() -> None:
    print("\n=== forbidden transition (publish before review) ===")
    pilot = Pilot(build_machine())
    try:
        pilot.step("publish")
    except TransitionError as exc:
        print(f"blocked as expected: {exc}")
        print(f"allowed right now:   {pilot.allowed_tools()}")


def demo_loop_limit() -> None:
    print("\n=== loop limit (too many research iterations) ===")
    # max_state_visits=3 => initial visit + 2 searches, the 3rd search trips it.
    pilot = Pilot(build_machine(), max_state_visits=3)
    try:
        pilot.step("search")
        pilot.step("search")
        pilot.step("search")
    except LoopLimitExceeded as exc:
        print(f"blocked as expected: {exc}")


def demo_budget() -> None:
    print("\n=== budget cap ($5) ===")
    pilot = Pilot(build_machine(), budget=5.0)
    try:
        pilot.step("search", cost=3.0)
        pilot.step("search", cost=3.0)  # 6.0 > 5.0
    except BudgetExceeded as exc:
        print(f"blocked as expected: {exc}")
        print(f"spent before block:  {pilot.cost_spent:.2f}")


def main() -> None:
    demo_happy_path()
    demo_forbidden_transition()
    demo_loop_limit()
    demo_budget()
    print("\nAll demos ran. statepilot enforced every rule deterministically.")


if __name__ == "__main__":
    main()
