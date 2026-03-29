"""CollectTransferDetailsUseCase — validate and store a single transfer field."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from send_money.domain.entities import TransferDraft
from send_money.domain.enums import DeliveryMethod
from send_money.domain.errors import InvalidFieldError
from send_money.domain.repositories import CorridorRepository


class CollectTransferDetailsUseCase:
    def __init__(self, corridor_repository: CorridorRepository) -> None:
        self._corridors = corridor_repository

    async def execute(
        self, draft_dict: dict, field_name: str, field_value: str
    ) -> TransferDraft:
        """Validate field_value for field_name and return the updated draft."""
        draft = TransferDraft.from_state_dict(draft_dict) if draft_dict else TransferDraft()

        match field_name:
            case "destination_country":
                await self._set_country(draft, field_value)
            case "amount":
                self._set_amount(draft, field_value)
            case "currency":
                self._set_currency(draft, field_value)
            case "beneficiary_name":
                self._set_beneficiary_name(draft, field_value)
            case "beneficiary_account":
                self._set_beneficiary_account(draft, field_value)
            case "delivery_method":
                await self._set_delivery_method(draft, field_value)
            case _:
                raise InvalidFieldError(field_name, "Unknown field name.")

        return draft

    # ── Field setters ────────────────────────────────────────

    async def _set_country(self, draft: TransferDraft, value: str) -> None:
        from send_money.domain.enums import format_country
        code = value.strip().upper()
        supported = await self._corridors.get_supported_countries()
        if code not in supported:
            labels = [format_country(c) for c in supported]
            raise InvalidFieldError(
                "destination_country",
                f"'{code}' is not supported. Supported: {', '.join(labels)}",
            )
        draft.destination_country = code
        # Reset delivery_method when country changes — old choice may be invalid
        draft.delivery_method = None
        # Reset calculated fields
        draft.destination_currency = None
        draft.fee_units = None
        draft.fee_nanos = None
        draft.receive_amount_units = None
        draft.receive_amount_nanos = None
        draft.status = draft.status.__class__.COLLECTING

    def _set_amount(self, draft: TransferDraft, value: str) -> None:
        try:
            amount = Decimal(value.strip().replace(",", ""))
        except InvalidOperation:
            raise InvalidFieldError("amount", f"'{value}' is not a valid number.")
        if amount <= 0:
            raise InvalidFieldError("amount", "Amount must be greater than zero.")

        from send_money.domain.value_objects import Money

        money = Money.from_decimal(amount, draft.amount_currency or "USD")
        draft.amount_units = money.units
        draft.amount_nanos = money.nanos
        # Reset downstream calculated fields
        draft.fee_units = None
        draft.fee_nanos = None
        draft.receive_amount_units = None
        draft.receive_amount_nanos = None

    def _set_currency(self, draft: TransferDraft, value: str) -> None:
        code = value.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise InvalidFieldError("currency", f"'{code}' is not a valid ISO 4217 code.")
        draft.amount_currency = code
        draft.source_currency = code

    def _set_beneficiary_name(self, draft: TransferDraft, value: str) -> None:
        name = value.strip()
        if len(name) < 2:
            raise InvalidFieldError("beneficiary_name", "Name is too short.")
        draft.beneficiary_name = name

    def _set_beneficiary_account(self, draft: TransferDraft, value: str) -> None:
        account = value.strip()
        if not account:
            raise InvalidFieldError("beneficiary_account", "Account number cannot be empty.")
        draft.beneficiary_account = account

    async def _set_delivery_method(self, draft: TransferDraft, value: str) -> None:
        from send_money.domain.enums import format_country, format_delivery_method
        method = value.strip().upper().replace(" ", "_")
        try:
            dm = DeliveryMethod(method)
        except ValueError:
            labels = [format_delivery_method(m.value) for m in DeliveryMethod]
            raise InvalidFieldError(
                "delivery_method",
                f"'{method}' is not valid. Choose from: {', '.join(labels)}",
            )
        if draft.destination_country:
            supported = await self._corridors.get_delivery_methods(draft.destination_country)
            if method not in supported:
                supported_labels = [format_delivery_method(m) for m in supported]
                country_label = format_country(draft.destination_country)
                raise InvalidFieldError(
                    "delivery_method",
                    f"'{dm.display_name}' is not available for {country_label}. "
                    f"Available: {', '.join(supported_labels)}",
                )
        draft.delivery_method = dm
        # Reset calculated fields
        draft.fee_units = None
        draft.fee_nanos = None
        draft.receive_amount_units = None
        draft.receive_amount_nanos = None
