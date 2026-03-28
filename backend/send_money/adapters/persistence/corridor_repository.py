"""Corridor repository implementations."""
from __future__ import annotations

from typing import Optional

from asgiref.sync import sync_to_async

from send_money.domain.repositories import CorridorRepository


class DjangoCorridorRepository(CorridorRepository):
    """Reads corridor data from the Django-managed `corridors` table."""

    async def get_supported_countries(self) -> list[str]:
        @sync_to_async
        def _query() -> list[str]:
            from send_money.adapters.persistence.django_models import Corridor

            return list(
                Corridor.objects.filter(is_active=True)
                .values_list("country_code", flat=True)
                .distinct()
                .order_by("country_code")
            )

        return await _query()

    async def get_delivery_methods(self, country_code: str) -> list[str]:
        @sync_to_async
        def _query() -> list[str]:
            from send_money.adapters.persistence.django_models import Corridor

            return list(
                Corridor.objects.filter(country_code=country_code, is_active=True)
                .values_list("delivery_method", flat=True)
                .order_by("delivery_method")
            )

        return await _query()

    async def get_destination_currency(self, country_code: str) -> Optional[str]:
        @sync_to_async
        def _query() -> Optional[str]:
            from send_money.adapters.persistence.django_models import Corridor

            corridor = (
                Corridor.objects.filter(country_code=country_code, is_active=True)
                .order_by("id")
                .first()
            )
            return corridor.currency_code if corridor else None

        return await _query()

    async def is_supported(self, country_code: str, delivery_method: str) -> bool:
        @sync_to_async
        def _query() -> bool:
            from send_money.adapters.persistence.django_models import Corridor

            return Corridor.objects.filter(
                country_code=country_code,
                delivery_method=delivery_method,
                is_active=True,
            ).exists()

        return await _query()


class InMemoryCorridorRepository(CorridorRepository):
    """In-memory corridor repository for tests — no database required."""

    _CORRIDORS: dict[str, dict] = {
        "MX": {"methods": ["BANK_DEPOSIT", "CASH_PICKUP", "MOBILE_WALLET"], "currency": "MXN"},
        "CO": {"methods": ["BANK_DEPOSIT", "CASH_PICKUP"], "currency": "COP"},
        "GT": {"methods": ["BANK_DEPOSIT", "CASH_PICKUP"], "currency": "GTQ"},
        "PH": {"methods": ["BANK_DEPOSIT", "MOBILE_WALLET"], "currency": "PHP"},
        "IN": {"methods": ["BANK_DEPOSIT"], "currency": "INR"},
        "GB": {"methods": ["BANK_DEPOSIT"], "currency": "GBP"},
    }

    async def get_supported_countries(self) -> list[str]:
        return sorted(self._CORRIDORS.keys())

    async def get_delivery_methods(self, country_code: str) -> list[str]:
        return self._CORRIDORS.get(country_code, {}).get("methods", [])

    async def get_destination_currency(self, country_code: str) -> Optional[str]:
        return self._CORRIDORS.get(country_code, {}).get("currency")

    async def is_supported(self, country_code: str, delivery_method: str) -> bool:
        methods = self._CORRIDORS.get(country_code, {}).get("methods", [])
        return delivery_method in methods
