"""Simulated implementations of ExchangeRateService and FeeService.

These stand in for real external API calls.  Swap them in container.py for
real implementations without touching any other code (Open/Closed principle).
"""

from __future__ import annotations

from decimal import Decimal

from send_money.application.ports import ExchangeRateService, FeeService
from send_money.domain.repositories import ExchangeRateRepository
from send_money.domain.value_objects import Money

# Fallback FX rates vs USD (used when the exchange_rates table has no row)
_RATES: dict[str, Decimal] = {
    "MXN": Decimal("17.45"),
    "COP": Decimal("4120.50"),
    "GTQ": Decimal("7.72"),
    "PHP": Decimal("56.30"),
    "INR": Decimal("83.12"),
    "GBP": Decimal("0.79"),
    "EUR": Decimal("0.92"),
    "USD": Decimal("1.00"),
}

# Flat fee per corridor (country, delivery_method) → USD amount as string
_FEES: dict[tuple[str, str], str] = {
    ("MX", "BANK_DEPOSIT"): "2.99",
    ("MX", "CASH_PICKUP"): "3.99",
    ("MX", "MOBILE_WALLET"): "1.99",
    ("CO", "BANK_DEPOSIT"): "3.49",
    ("CO", "CASH_PICKUP"): "4.49",
    ("GT", "BANK_DEPOSIT"): "3.99",
    ("GT", "CASH_PICKUP"): "4.99",
    ("PH", "BANK_DEPOSIT"): "2.49",
    ("PH", "MOBILE_WALLET"): "1.49",
    ("IN", "BANK_DEPOSIT"): "0.99",
    ("GB", "BANK_DEPOSIT"): "1.99",
}


class SimulatedExchangeRateService(ExchangeRateService):
    def __init__(
        self, exchange_rate_repository: ExchangeRateRepository | None = None
    ) -> None:
        self._repo = exchange_rate_repository

    async def get_rate(
        self, source_currency: str, destination_currency: str
    ) -> Decimal:
        if source_currency == destination_currency:
            return Decimal("1.00")

        # Query DB first; fall back to hardcoded rates if not found
        if self._repo is not None:
            db_rate = await self._repo.get_rate(source_currency, destination_currency)
            if db_rate is not None:
                return db_rate

        # Fallback: cross via USD
        to_usd = Decimal("1") / _RATES.get(source_currency, Decimal("1"))
        to_dest = _RATES.get(destination_currency, Decimal("1"))
        return (to_usd * to_dest).quantize(Decimal("0.000001"))


class SimulatedFeeService(FeeService):
    async def calculate_fee(
        self,
        amount_units: int,
        amount_nanos: int,
        destination_country: str,
        delivery_method: str,
    ) -> tuple[int, int]:
        fee_str = _FEES.get((destination_country, delivery_method), "2.99")
        fee_money = Money.from_decimal(Decimal(fee_str), "USD")
        return fee_money.units, fee_money.nanos
