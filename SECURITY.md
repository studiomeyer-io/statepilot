# Security Policy

## Scope

`statepilot` is a small, dependency-free library that enforces state-machine
transitions, loop limits, cost budgets, and step caps at runtime. It does not
make network calls, read or write files (except the explicit, opt-in
`StateMachine.from_yaml_file(path)` read), execute arbitrary code, or handle
secrets. A `Pilot` enforces a single agent run and is not thread-safe — use one
pilot per run rather than sharing one across threads.

The most security-relevant promise it makes is **correct enforcement**: if a tool
call is not allowed by the state machine, `Pilot.step` must raise rather than
silently permit it. A bug that lets a forbidden transition, an over-budget step,
or a runaway loop slip through is treated as a security issue, not just a
correctness bug, because downstream agents may rely on these guards as a safety
boundary.

## Supported versions

Pre-1.0, only the latest released `0.x` version receives fixes. Once `1.0` ships,
this section will list the supported release lines.

| Version | Supported |
| ------- | --------- |
| latest `0.x` | yes |
| older | no |

## Reporting a vulnerability

Please report suspected vulnerabilities privately rather than opening a public
issue:

- Preferred: open a **GitHub Security Advisory** via the repository's
  *Security → Report a vulnerability* tab.
- Alternatively: email **security@studiomeyer.io** with details and, ideally, a
  minimal reproduction.

We aim to acknowledge reports within a few business days. Please give us a
reasonable window to ship a fix before any public disclosure. We will credit
reporters who wish to be named once a fix is released.

## Out of scope

- Whether your *own* state machine definition is the right policy — statepilot
  enforces the machine you give it; designing a safe machine is on you.
- Behaviour of the optional, experimental LangGraph adapter when used outside its
  documented "guard a node" contract.
