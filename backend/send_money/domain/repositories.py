"""Repository interfaces (ABCs) — innermost layer.

Implementations live in adapters/persistence/ and are injected via the
DI container.  No framework imports allowed here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from .entities import Beneficiary, TransferDraft, UserAccount


class TransferRepository(ABC):
    @abstractmethod
    async def save(self, draft: TransferDraft) -> TransferDraft:
        """Persist a confirmed transfer draft, returning the saved entity."""

    @abstractmethod
    async def save_and_deduct(
        self,
        draft: TransferDraft,
        user_id: str,
        deduct_units: int,
        deduct_nanos: int,
    ) -> TransferDraft:
        """Atomically save a transfer AND deduct balance from the user's account.

        Uses a single transaction.atomic() block. Raises InsufficientFundsError
        if the account balance is too low.
        """

    @abstractmethod
    async def get_by_id(self, transfer_id: str) -> TransferDraft | None:
        """Return a transfer by its primary key, or None if not found."""


class CorridorRepository(ABC):
    @abstractmethod
    async def get_supported_countries(self) -> list[str]:
        """Return ISO 3166-1 alpha-2 codes of all active destination countries."""

    @abstractmethod
    async def get_delivery_methods(self, country_code: str) -> list[str]:
        """Return active delivery methods for the given country."""

    @abstractmethod
    async def get_destination_currency(self, country_code: str) -> str | None:
        """Return the primary ISO 4217 currency for the given country, or None."""

    @abstractmethod
    async def is_supported(self, country_code: str, delivery_method: str) -> bool:
        """Return True when the country/method corridor is active."""


class ExchangeRateRepository(ABC):
    @abstractmethod
    async def get_rate(
        self, source_currency: str, destination_currency: str
    ) -> Decimal | None:
        """Return the active exchange rate, or None if not found."""


class UserAccountRepository(ABC):
    @abstractmethod
    async def create(self, account: UserAccount) -> UserAccount:
        """Persist a new user account."""

    @abstractmethod
    async def get_by_username(self, username: str) -> UserAccount | None:
        """Return an account by username, or None if not found."""

    @abstractmethod
    async def get_by_id(self, user_id: str) -> UserAccount | None:
        """Return an account by ID, or None if not found."""

    @abstractmethod
    async def add_funds(self, user_id: str, units: int, nanos: int) -> UserAccount:
        """Add funds to the account. Returns the updated account."""

    @abstractmethod
    async def deduct_funds(self, user_id: str, units: int, nanos: int) -> UserAccount:
        """Atomically deduct funds (SELECT FOR UPDATE).

        Raises InsufficientFundsError.
        """


class BeneficiaryRepository(ABC):
    @abstractmethod
    async def create(self, beneficiary: Beneficiary) -> Beneficiary:
        """Persist a new beneficiary, returning the saved entity."""

    @abstractmethod
    async def get_by_id(self, beneficiary_id: str) -> Beneficiary | None:
        """Return a beneficiary by primary key, or None if not found."""

    @abstractmethod
    async def list_for_user(self, user_id: str) -> list[Beneficiary]:
        """Return all beneficiaries belonging to a user, ordered by name."""

    @abstractmethod
    async def find_by_name_and_user(self, user_id: str, name: str) -> list[Beneficiary]:
        """Case-insensitive name lookup — returns ALL entries for the name.

        A beneficiary may have multiple entries with different delivery methods.
        """

    @abstractmethod
    async def update(self, beneficiary: Beneficiary) -> Beneficiary:
        """Persist changes to an existing beneficiary."""


class AuditLogRepository(ABC):
    @abstractmethod
    async def log(
        self,
        transfer_id: str,
        session_id: str,
        user_id: str,
        action: str,
        langfuse_trace_id: str = "",
        langfuse_observation_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist an audit log entry for the given transfer."""
