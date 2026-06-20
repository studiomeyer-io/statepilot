"""Shared fixtures for the statepilot test suite."""

from __future__ import annotations

import pytest

from statepilot import StateMachine


@pytest.fixture
def publish_machine() -> StateMachine:
    """A realistic content pipeline: research -> draft -> review -> published.

    * ``search`` loops within ``research``.
    * ``write_draft`` moves research -> draft.
    * ``revise`` moves review -> draft (sending it back).
    * ``review`` moves draft -> review.
    * ``publish`` moves review -> published (terminal).
    """
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


@pytest.fixture
def linear_machine() -> StateMachine:
    """A minimal two-step linear machine: a -> b (terminal)."""
    return (
        StateMachine.builder()
        .initial("a")
        .transition("a", "b", tool="go")
        .terminal("b")
        .build()
    )
