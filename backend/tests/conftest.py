"""Shared pytest fixtures."""
from __future__ import annotations

import os

import django
import pytest

# Ensure backend/ is on sys.path for all tests (also set in pyproject.toml)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


@pytest.fixture(scope="session")
def django_db_setup():
    """Use pytest-django's test database for integration tests."""


# ── In-memory fakes shared across unit tests ─────────────────────────────────

@pytest.fixture
def in_memory_corridor_repo():
    from send_money.adapters.persistence.corridor_repository import InMemoryCorridorRepository

    return InMemoryCorridorRepository()


@pytest.fixture
def in_memory_session_service():
    from google.adk.sessions import InMemorySessionService

    return InMemorySessionService()


@pytest.fixture
def mock_transfer_repo():
    """Simple in-memory transfer repository for unit tests."""
    from send_money.domain.entities import TransferDraft
    from send_money.domain.repositories import TransferRepository

    class InMemoryTransferRepository(TransferRepository):
        def __init__(self) -> None:
            self._store: dict[str, TransferDraft] = {}

        async def save(self, draft: TransferDraft) -> TransferDraft:
            self._store[draft.id] = draft
            return draft

        async def get_by_id(self, transfer_id: str):
            return self._store.get(transfer_id)

    return InMemoryTransferRepository()


@pytest.fixture
def mock_tool_context():
    """Minimal ToolContext mock with a mutable state dict."""

    class _Session:
        id = "test-session"
        user_id = "test-user"

    class _InvocationContext:
        session = _Session()

    class _MockContext:
        def __init__(self) -> None:
            self.state: dict = {"transfer_draft": {}}
            self.invocation_id = "test-invocation"
            self.user_id = "test-user"
            self.invocation_context = _InvocationContext()

    return _MockContext()
