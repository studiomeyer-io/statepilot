"""Optional, weakly-coupled adapters for orchestration frameworks.

Importing :mod:`statepilot.adapters` does **not** import any third-party
framework. Each adapter is written against the framework's stable *callable
contract* rather than its internal API, so it keeps working across framework
versions and needs the framework only at the call site, not at import time.
"""

from __future__ import annotations

from .langgraph import guard_node

__all__ = ["guard_node"]
