<!-- studiomeyer-mcp-stack-banner:start -->
> **Part of the [StudioMeyer MCP Stack](https://studiomeyer.io)** — Built in Mallorca 🌴 · ⭐ if you use it
<!-- studiomeyer-mcp-stack-banner:end -->

# statepilot

[![PyPI](https://img.shields.io/pypi/v/statepilot.svg)](https://pypi.org/project/statepilot/)
[![Python](https://img.shields.io/pypi/pyversions/statepilot.svg)](https://pypi.org/project/statepilot/)
[![CI](https://github.com/studiomeyer-io/statepilot/actions/workflows/ci.yml/badge.svg)](https://github.com/studiomeyer-io/statepilot/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/studiomeyer-io/statepilot/badge)](https://scorecard.dev/viewer/?uri=github.com/studiomeyer-io/statepilot)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Deterministic state-machine guards for AI-agent workflows.**

Define a state machine, then enforce — at *runtime* — which tools your agent may
call, in which order, with loop detection, a cost budget, and a hard step cap.
The agent only gets to do what the state machine allows. Anything else raises.

Zero runtime dependencies in the core. Fully typed. Python 3.10+.

```bash
pip install statepilot
```

## The problem

A recurring theme in 2026 agent tooling is "wrap the non-deterministic LLM in
deterministic code." A few data points that frame the gap:

- **Statewright** (Rust + MCP) put deterministic state machines for agents on the
  map — it reached the [Hacker News front page](https://news.ycombinator.com/)
  and lives at <https://github.com/statewright/statewright>. The framing clearly
  resonates.
- **llm-canary** ships *policy gates for agent traces* — tool order, cost
  budgets, runaway-loop checks — but as a **post-hoc test layer** over recorded
  traces, not as runtime enforcement.
- Orchestrators like **LangGraph**, **CrewAI** and the **OpenAI Agents SDK** are
  excellent at *routing*, but they don't hand you a small, hard rule that says
  "tool X is illegal in state Y, full stop."

The missing piece is a **Python-native runtime guard**: a thin layer you put in
front of every tool call that enforces the allowed transitions and trips on
loops and budget overruns. That is what statepilot is.

It does not orchestrate, plan, or call your LLM. It is the bouncer at the door.

## Quickstart (Python builder)

```python
from statepilot import StateMachine, Pilot

machine = (
    StateMachine.builder()
    .initial("research")
    .transition("research", "research", tool="search")      # looping allowed...
    .transition("research", "draft", tool="write_draft")
    .transition("draft", "review", tool="review")
    .transition("review", "draft", tool="revise")           # send it back
    .transition("review", "published", tool="publish")
    .terminal("published")
    .build()
)

pilot = Pilot(machine, budget=5.0, max_state_visits=4, max_steps=20)

pilot.step("search", cost=0.5)        # ok, still in "research"
pilot.step("write_draft", cost=1.0)   # -> "draft"
pilot.step("review")                  # -> "review"
pilot.step("publish")                 # -> "published" (terminal)

pilot.step("review")                  # raises TransitionError: terminal state
```

Every accepted step is recorded:

```python
for record in pilot.history:
    print(record.index, record.source, "--", record.tool, "->", record.dest)
```

## The `@guarded` decorator

Bind your actual tool functions to the pilot. The guard runs **before** the
function body, so a violation means the body never executes.

```python
from statepilot import StateMachine, Pilot, guarded, GuardViolation

machine = (
    StateMachine.builder()
    .initial("research")
    .transition("research", "research", tool="search")
    .transition("research", "draft", tool="write_draft")
    .terminal("draft")
    .build()
)
pilot = Pilot(machine, budget=5.0)

@guarded(pilot, cost=1.0)                 # tool name defaults to the function name
def search(query: str) -> list[str]:
    return real_search(query)

@guarded(pilot, tool="write_draft")       # or name it explicitly
def make_draft(notes: list[str]) -> str:
    return real_draft(notes)

search("agent guardrails")                # advances the machine, charges 1.0
make_draft(["..."])                       # -> "draft"

try:
    make_draft(["..."])                   # already terminal
except GuardViolation as exc:
    print("blocked:", exc)
```

## YAML definition

Prefer config over code? Define the machine in YAML and load it. (YAML support is
an optional extra: `pip install statepilot[yaml]`.)

```yaml
# pipeline.yaml
initial: research
terminal:
  - published
transitions:
  - {from: research, to: research, tool: search}
  - {from: research, to: draft,    tool: write_draft}
  - {from: draft,    to: review,   tool: review}
  - {from: review,   to: published, tool: publish}
```

```python
from statepilot import StateMachine, Pilot

machine = StateMachine.from_yaml_file("pipeline.yaml")  # from a file
# or: StateMachine.from_yaml(yaml_string)               # from an inline string
pilot = Pilot(machine, budget=5.0)
```

`states` may be omitted — it is inferred from `initial`, `terminal`, and every
state named in `transitions`. `StateMachine.from_dict(...)` accepts the same
shape if you already have a dict.

## A realistic agent example

"Research, then draft, then review, then publish. Never publish before review.
Allow at most 3 research loops. Stop if cost exceeds \$5."

```python
from statepilot import StateMachine, Pilot, guarded, GuardViolation

machine = (
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

# initial visit counts as 1, so max_state_visits=4 allows 3 extra research loops
pilot = Pilot(machine, budget=5.0, max_state_visits=4, max_steps=25)

@guarded(pilot, cost=0.8)
def search(q: str) -> str: ...

@guarded(pilot, cost=1.2)
def write_draft(notes: str) -> str: ...

@guarded(pilot)
def review(draft: str) -> bool: ...

@guarded(pilot, cost=0.3)
def publish(draft: str) -> str: ...
```

The agent loop calls these as it sees fit. statepilot makes the illegal paths
impossible:

- calling `publish()` while still in `research` -> `TransitionError`
- a 4th `search()` loop -> `LoopLimitExceeded`
- cumulative cost over \$5 -> `BudgetExceeded`
- more than 25 steps -> `StepLimitExceeded`

A runnable version is in [`examples/research_pipeline.py`](examples/research_pipeline.py).

## Why deterministic guards

LLMs are probabilistic. Most of the time the model follows the plan; occasionally
it calls `publish` before `review`, gets stuck re-searching the same thing, or
burns the budget. "Most of the time" is not a guarantee, and prompt-only
constraints are suggestions, not enforcement.

A state machine turns those soft expectations into a hard contract that lives in
code, runs on every tool call, and is trivial to unit-test. You get:

- **Safety** — illegal tool sequences cannot happen; they raise instead. The
  guards fail *closed*: invalid input (e.g. a `NaN` cost) raises rather than
  silently letting a step through.
- **Cost control** — a real budget cap, enforced before the expensive call runs.
- **Loop protection** — runaway repetition trips a clear, typed exception.
- **Auditability** — `pilot.history` and `pilot.to_trace()` give you a complete,
  JSON-serialisable record of what the agent actually did.

It is intentionally small. The whole core is a `StateMachine` plus a `Pilot`, and
the runtime cost is a dict lookup and a few integer comparisons per step.

## API reference

### `StateMachine`

Immutable, validated machine definition. Carries no runtime state.

- `StateMachine.builder(initial=None) -> StateMachineBuilder` — fluent builder.
- `StateMachine.from_dict(data) -> StateMachine` — build from a mapping.
- `StateMachine.from_yaml(text) -> StateMachine` — build from an inline YAML
  string (needs the `yaml` extra).
- `StateMachine.from_yaml_file(path) -> StateMachine` — build from a YAML file
  (needs the `yaml` extra).
- `.to_dict()` — round-trips with `from_dict`.
- `.allowed_tools(state) -> tuple[str, ...]`
- `.resolve(state, tool) -> str | None` — destination, or `None` if disallowed.
- `.is_terminal(state) -> bool`

### `StateMachineBuilder`

- `.initial(state)`, `.state(*states)`, `.transition(src, dest, *, tool)`,
  `.terminal(*states)`, `.build()`. Every mutator returns `self`.

### `Pilot`

Stateful runtime enforcer. Construct with the machine and optional limits:

```python
Pilot(
    machine,
    budget=None,              # cumulative cost cap (finite or None)
    max_steps=None,           # total steps cap
    max_state_visits=None,    # per-state visit cap (initial state counts as 1)
    max_consecutive_tool=None # same tool back-to-back cap
)
```

- `.step(tool, *, cost=0.0) -> str` — validate + apply; returns the new state.
  Raises on violation; state is unchanged on failure. `cost` must be finite
  and `>= 0` — a non-finite cost (`NaN`/`inf`) raises `ValueError` rather than
  silently slipping past the budget (fail-closed).
- `.can(tool, *, cost=0.0) -> bool` — pure check, never mutates, never raises
  for a guard decision (an invalid `cost` still raises `ValueError`, like
  `.step`).
- `.allowed_tools() -> tuple[str, ...]`, `.state`, `.done`, `.steps_taken`,
  `.cost_spent`, `.history`.
- `.to_trace() -> dict` — JSON-serialisable run trace.
- `.reset()` — back to the initial state, clears cost/counters/history.

### `@guarded(pilot, *, tool=None, cost=0.0)`

Decorator that calls `pilot.step(...)` before the function body. `tool` defaults
to the function name.

### Exceptions

```
StatepilotError
├── StateMachineError          # invalid machine definition (definition-time)
└── GuardViolation             # runtime rule broken — catch this for "agent misbehaved"
    ├── TransitionError        # tool not allowed in the current state
    ├── LoopLimitExceeded      # state revisited / tool repeated too often
    ├── BudgetExceeded         # cumulative cost over budget
    └── StepLimitExceeded      # too many total steps
```

## LangGraph adapter (experimental)

If you orchestrate with [LangGraph](https://github.com/langchain-ai/langgraph),
`statepilot.adapters.guard_node` wraps a node so the pilot guards it:

```python
from statepilot import StateMachine, Pilot
from statepilot.adapters import guard_node
# from langgraph.graph import StateGraph

pilot = Pilot(machine, budget=5.0)
# graph = StateGraph(MyState)
# graph.add_node("research", guard_node(pilot, research_node, cost=1.0))
# graph.add_node("draft",    guard_node(pilot, draft_node))
```

It targets LangGraph's stable *node contract* (a callable `state -> partial
state dict`) and **never imports langgraph itself**, so it adds no import-time
dependency and does not break when the LangGraph API changes. It is deliberately
minimal and marked experimental — conditional edges, `Send` fan-out, and
checkpoint/resume are out of scope. For full control, just drive the `Pilot`
inside your own node functions; that path is fully supported.

The adapter needs no extra dependency — it works with any callable. Install
LangGraph in your own project if you use it.

## Concurrency

A `Pilot` holds the mutable state of **one** agent run and is **not
thread-safe** — use one pilot per run, don't share it across threads, and call
`pilot.reset()` to reuse it. `pilot.history` is an immutable snapshot (a tuple),
so reading or logging it can never desync the run's guards.

## Status

Beta (`0.1.0`). The core API (`StateMachine`, `Pilot`, `@guarded`) is what we
intend to keep stable. No benchmarks are claimed — the design goal is
correctness and a tiny footprint, not throughput. Issues and PRs welcome.

## Related StudioMeyer open-source tools

Other focused, production-grade tools for building and operating AI agents & MCP servers:

- [skilldoctor](https://github.com/studiomeyer-io/skilldoctor) — linter + security scanner for agent skill files (SKILL.md / AGENTS.md / subagents)
- [mcp-armor](https://github.com/studiomeyer-io/mcp-armor) — runtime defense sidecar for MCP servers
- [mcp-gauntlet](https://github.com/studiomeyer-io/mcp-gauntlet) — fuzz + load test MCP servers before you ship
- [mcp-otel](https://github.com/studiomeyer-io/mcp-otel) — W3C Trace Context → OpenTelemetry bridge for MCP
- [mcp-cache-kit](https://github.com/studiomeyer-io/mcp-cache-kit) — leak-safe SEP-2549 caching for MCP

## License

MIT © 2026 StudioMeyer. See [LICENSE](LICENSE).
