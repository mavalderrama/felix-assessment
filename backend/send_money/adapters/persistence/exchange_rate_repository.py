"""Exchange rate repository — reads from the exchange_rates table."""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from asgiref.sync import sync_to_async

from send_money.domain.repositories import ExchangeRateRepository


class DjangoExchangeRateRepository(ExchangeRateRepository):
    async def get_rate(
        self, source_currency: str, destination_currency: str
    ) -> Decimal | None:
        @sync_to_async
        def _get() -> Decimal | None:
            from send_money.adapters.persistence.django_models import ExchangeRate

            try:
                row = ExchangeRate.objects.get(
                    source_currency=source_currency,
                    destination_currency=destination_currency,
                    is_active=True,
                )
                return cast(Decimal, row.rate)
            except ExchangeRate.DoesNotExist:
                return None

        return await _get()
