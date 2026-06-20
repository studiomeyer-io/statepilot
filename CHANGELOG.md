# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-20

Initial release.

### Added

- `StateMachine` — immutable, validated state-machine definition with a fluent
  builder, `from_dict`, `from_yaml` (optional `yaml` extra), and `to_dict`
  round-trip.
- `Pilot` — runtime guard enforcing allowed transitions, terminal states, a
  per-state loop limit, a consecutive-tool loop limit, a cumulative cost budget,
  and a hard step cap. Records a full `history` and exports a JSON-serialisable
  `to_trace()`.
- `@guarded` decorator to bind tool functions to a `Pilot`.
- Typed exception hierarchy: `StatepilotError`, `StateMachineError`,
  `GuardViolation`, `TransitionError`, `LoopLimitExceeded`, `BudgetExceeded`,
  `StepLimitExceeded`.
- Experimental `statepilot.adapters.guard_node` for LangGraph (targets the stable
  node-callable contract; never imports langgraph).
- Zero runtime dependencies in the core. Fully typed with a `py.typed` marker.

[0.1.0]: https://github.com/studiomeyer-io/statepilot/releases/tag/v0.1.0
