"""Service interfaces (ports) — application layer.

Simulated implementations live in infrastructure/simulated_services.py.
Real implementations would call external FX / fee APIs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal


class ExchangeRateService(ABC):
    @abstractmethod
    async def get_rate(
        self, source_currency: str, destination_currency: str
    ) -> Decimal:
        """Return the exchange rate from source to destination currency."""


class FeeService(ABC):
    @abstractmethod
    async def calculate_fee(
        self,
        amount_units: int,
        amount_nanos: int,
        destination_country: str,
        delivery_method: str,
    ) -> tuple[int, int]:
        """Return the fee as (units, nanos)."""
