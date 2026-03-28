"""ValidateTransferUseCase — verify corridor and calculate fees + FX."""
from __future__ import annotations

from send_money.domain.entities import TransferDraft
from send_money.domain.enums import TransferStatus
from send_money.domain.errors import InvalidFieldError, UnsupportedCorridorError
from send_money.domain.repositories import CorridorRepository
from send_money.domain.value_objects import Money
from send_money.application.ports import ExchangeRateService, FeeService


class ValidateTransferUseCase:
    def __init__(
        self,
        corridor_repository: CorridorRepository,
        exchange_rate_service: ExchangeRateService,
        fee_service: FeeService,
    ) -> None:
        self._corridors = corridor_repository
        self._fx = exchange_rate_service
        self._fees = fee_service

    async def execute(self, draft_dict: dict) -> TransferDraft:
        """Validate the draft, compute fees and receive amount, return updated draft."""
        draft = TransferDraft.from_state_dict(draft_dict)

        if not draft.is_complete:
            raise InvalidFieldError(
                "transfer",
                f"Missing required fields: {', '.join(draft.missing_fields)}",
            )

        # Corridor check
        country = draft.destination_country
        method = str(draft.delivery_method)
        if not await self._corridors.is_supported(country, method):
            raise UnsupportedCorridorError(country, method)

        # Resolve destination currency
        dest_currency = await self._corridors.get_destination_currency(country)
        source_currency = draft.amount_currency or "USD"
        draft.source_currency = source_currency
        draft.destination_currency = dest_currency

        # Calculate fee
        fee_units, fee_nanos = await self._fees.calculate_fee(
            draft.amount_units or 0,
            draft.amount_nanos or 0,
            country,
            method,
        )
        draft.fee_units = fee_units
        draft.fee_nanos = fee_nanos

        # Calculate receive amount using exchange rate
        rate = await self._fx.get_rate(source_currency, dest_currency or source_currency)
        send_money = Money(
            units=draft.amount_units or 0,
            nanos=draft.amount_nanos or 0,
            currency_code=source_currency,
        )
        receive_decimal = send_money.to_decimal() * rate
        receive_money = Money.from_decimal(receive_decimal, dest_currency or source_currency)
        draft.receive_amount_units = receive_money.units
        draft.receive_amount_nanos = receive_money.nanos

        draft.status = TransferStatus.VALIDATED
        return draft
