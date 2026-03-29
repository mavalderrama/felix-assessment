"""Shared pytest fixtures."""

from __future__ import annotations

import os
from typing import Any

import pytest

# Ensure backend/ is on sys.path for all tests (also set in pyproject.toml)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


@pytest.fixture(scope="session")
def django_db_setup() -> None:
    """Use pytest-django's test database for integration tests."""


# ── In-memory fakes shared across unit tests ─────────────────────────────────


@pytest.fixture
def in_memory_corridor_repo() -> Any:
    from send_money.adapters.persistence.corridor_repository import (
        InMemoryCorridorRepository,
    )

    return InMemoryCorridorRepository()


@pytest.fixture
def in_memory_session_service() -> Any:
    from google.adk.sessions import InMemorySessionService

    return InMemorySessionService()  # type: ignore[no-untyped-call]


@pytest.fixture
def mock_transfer_repo() -> Any:
    """Simple in-memory transfer repository for unit tests."""
    from send_money.domain.entities import TransferDraft
    from send_money.domain.repositories import TransferRepository

    class InMemoryTransferRepository(TransferRepository):
        def __init__(self) -> None:
            self._store: dict[str, TransferDraft] = {}
            self.last_deduction: tuple[Any, ...] | None = None

        async def save(self, draft: TransferDraft) -> TransferDraft:
            self._store[draft.id] = draft  # type: ignore[index]
            return draft

        async def save_and_deduct(
            self,
            draft: TransferDraft,
            user_id: str,
            deduct_units: int,
            deduct_nanos: int,
        ) -> TransferDraft:
            self._store[draft.id] = draft  # type: ignore[index]
            self.last_deduction = (user_id, deduct_units, deduct_nanos)
            return draft

        async def get_by_id(self, transfer_id: str) -> TransferDraft | None:
            return self._store.get(transfer_id)

    return InMemoryTransferRepository()


@pytest.fixture
def in_memory_beneficiary_repo() -> Any:
    from send_money.adapters.persistence.beneficiary_repository import (
        InMemoryBeneficiaryRepository,
    )

    return InMemoryBeneficiaryRepository()


@pytest.fixture
def mock_tool_context() -> Any:
    """Minimal ToolContext mock with a mutable state dict."""

    class _Session:
        id = "test-session"
        user_id = "test-user"

    class _InvocationContext:
        session = _Session()

    class _MockContext:
        def __init__(self) -> None:
            self.state: dict[str, Any] = {"transfer_draft": {}}
            self.invocation_id = "test-invocation"
            self.user_id = "test-user"
            self.invocation_context = _InvocationContext()

    return _MockContext()
