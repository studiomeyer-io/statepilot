# Contributing to statepilot

Thanks for considering a contribution. statepilot is a **fail-closed guard**: a
forbidden transition must raise *before* the tool runs, every time. The bar for
new code is "it keeps the guard deterministic and fail-closed, and it ships with a
test" — and for anything touching enforcement, a test proving the illegal path
raises.

## Quick Start

```sh
git clone https://github.com/studiomeyer-io/statepilot
cd statepilot
pip install -e ".[dev]"     # or: uv sync --extra dev
ruff check .
ruff format --check .
mypy --strict src
pytest                       # parametrized over many machine definitions
python examples/research_pipeline.py
```

Python **3.10+**. CI runs the suite on 3.10, 3.11, and 3.12.

## What we accept

- **New guard semantics** — a new limit or transition rule, with a test that
  asserts both the allowed path passes **and** the forbidden path raises the right
  typed exception. `can()` and `step()` must stay consistent (one never lies about
  what the other will do).
- **New typed exceptions** under the `GuardViolation` hierarchy, when a failure
  mode deserves its own catch.
- **Bug fixes.** A failing test in your PR description is the fastest path to merge.
- **Docs.** Typo fixes, clarifications, ecosystem links.

## What we are slow on

- **Runtime dependencies.** The core is **zero-dependency** on purpose — that "tiny,
  sharp drop-in" is the whole pitch. `pyyaml` stays an optional `[yaml]` extra; a
  pydantic (or similar) runtime dep would undermine it. Open an issue first.
- **Importing LangGraph in the adapter.** `guard_node` targets LangGraph's stable
  *callable node contract* and never imports langgraph — so it adds no import-time
  dependency and doesn't break on LangGraph API churn. Keep it that way.
- **Orchestration features.** statepilot is the bouncer at the door, not a planner.
  Routing, conditional edges, and `Send` fan-out are out of scope by design.

## Pull Request Process

1. Open an issue or draft PR first for anything non-trivial.
2. One logical change per PR.
3. CI must be green: `ruff check`, `ruff format --check`, `mypy --strict`, `pytest`.
4. Add a `CHANGELOG.md` entry under `[Unreleased]`.
5. For security-impacting changes, see [SECURITY.md](SECURITY.md) — please email
   instead of opening a public issue.

## Coding Standards

- Zero runtime dependencies in the core (stdlib `dataclasses` + hand-rolled
  validation). Keep it that way.
- Fully typed, `mypy --strict` clean; the package ships a `py.typed` marker.
- Fail-closed is the invariant: if in doubt, raise. A guard that silently allows is
  a bug.
- `ruff` (line length 88) for lint + format.

## Testing

- Tests live in `tests/`, many parametrized over machine definitions (happy-path,
  forbidden-transition, loop-limit, budget, step-limit, terminal-state-block).
- New behavior needs a test that fails on `main` and passes with your patch.

## Releasing (maintainers)

- Bump `version` in `pyproject.toml` and add a dated `CHANGELOG.md` section.
- Tag `vX.Y.Z` on `main`. `publish.yml` uploads to PyPI via OIDC **Trusted
  Publishing** (configure the trusted publisher for `studiomeyer-io/statepilot`
  before the first tag).
- Verify on PyPI and with a clean-room `pip install statepilot` (zero-dep core).

## License

By contributing, you agree your work is licensed under the [MIT License](LICENSE).

## Code of Conduct

Be kind. Assume good faith. We are a small studio in Palma de Mallorca — no drama,
disagreement is fine, contempt is not.
