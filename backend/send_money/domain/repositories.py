"""Repository interfaces (ABCs) — innermost layer.

Implementations live in adapters/persistence/ and are injected via the
DI container.  No framework imports allowed here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import TransferDraft


class TransferRepository(ABC):
    @abstractmethod
    async def save(self, draft: TransferDraft) -> TransferDraft:
        """Persist a confirmed transfer draft, returning the saved entity."""

    @abstractmethod
    async def get_by_id(self, transfer_id: str) -> Optional[TransferDraft]:
        """Return a transfer by its primary key, or None if not found."""


class CorridorRepository(ABC):
    @abstractmethod
    async def get_supported_countries(self) -> list[str]:
        """Return ISO 3166-1 alpha-2 codes of all active destination countries."""

    @abstractmethod
    async def get_delivery_methods(self, country_code: str) -> list[str]:
        """Return active delivery methods for the given country."""

    @abstractmethod
    async def get_destination_currency(self, country_code: str) -> Optional[str]:
        """Return the primary ISO 4217 currency for the given country, or None."""

    @abstractmethod
    async def is_supported(self, country_code: str, delivery_method: str) -> bool:
        """Return True when the country/method corridor is active."""
