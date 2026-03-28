"""ADK tool functions for the Send Money Agent.

Tools are created via a closure factory so use-case dependencies are captured
at construction time — no global state, fully testable.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from send_money.infrastructure.container import Container


def create_tools(container: "Container") -> list[Callable]:
    """Return the list of tool callables, each closing over the container."""

    collect_uc = container.collect_uc
    validate_uc = container.validate_uc
    confirm_uc = container.confirm_uc
    corridors_uc = container.corridors_uc

    # ── Tool 1: update a single field ───────────────────────

    async def update_transfer_field(
        field_name: str,
        field_value: str,
        tool_context,
    ) -> dict:
        """Update one field in the transfer draft.

        Call this once per field.  For amount + currency provided together,
        call this function twice — once for 'amount', once for 'currency'.

        Args:
            field_name: The field to update. One of: destination_country,
                amount, currency, beneficiary_name, delivery_method.
            field_value: The value to set (always a string; numbers are parsed
                internally).
        """
        from send_money.domain.errors import DomainError

        draft_dict: dict = tool_context.state.get("transfer_draft", {})
        try:
            updated = await collect_uc.execute(draft_dict, field_name, field_value)
        except DomainError as exc:
            return {"status": "error", "field": field_name, "message": str(exc)}

        tool_context.state["transfer_draft"] = updated.to_state_dict()
        return {
            "status": "updated",
            "field": field_name,
            "value": field_value,
            "missing_fields": updated.missing_fields,
        }

    # ── Tool 2: validate the complete draft ─────────────────

    async def validate_transfer(tool_context) -> dict:
        """Validate the transfer draft and calculate fees and exchange rates.

        Call this once all required fields are set.  Returns a summary dict
        with the calculated fee and receive amount.
        """
        from send_money.domain.errors import DomainError
        from send_money.domain.value_objects import Money

        draft_dict: dict = tool_context.state.get("transfer_draft", {})
        try:
            validated = await validate_uc.execute(draft_dict)
        except DomainError as exc:
            return {"status": "error", "message": str(exc)}

        tool_context.state["transfer_draft"] = validated.to_state_dict()

        fee = Money(
            units=validated.fee_units or 0,
            nanos=validated.fee_nanos or 0,
            currency_code=validated.source_currency or "",
        )
        receive = Money(
            units=validated.receive_amount_units or 0,
            nanos=validated.receive_amount_nanos or 0,
            currency_code=validated.destination_currency or "",
        )
        send = Money(
            units=validated.amount_units or 0,
            nanos=validated.amount_nanos or 0,
            currency_code=validated.source_currency or "",
        )
        return {
            "status": "validated",
            "send_amount": str(send),
            "fee": str(fee),
            "destination_currency": validated.destination_currency,
            "receive_amount": str(receive),
            "destination_country": validated.destination_country,
            "beneficiary_name": validated.beneficiary_name,
            "delivery_method": str(validated.delivery_method),
        }

    # ── Tool 3: confirm and persist ─────────────────────────

    async def confirm_transfer(tool_context) -> dict:
        """Confirm and persist the transfer.  Call only after user explicitly agrees.

        Returns the confirmation code.
        """
        from send_money.domain.errors import DomainError

        draft_dict: dict = tool_context.state.get("transfer_draft", {})
        session_id: str = getattr(tool_context, "session_id", "") or ""
        user_id: str = getattr(tool_context, "user_id", "") or ""

        # Fallback: pull from invocation context if available
        if not session_id:
            try:
                session_id = tool_context.invocation_context.session.id
                user_id = tool_context.invocation_context.session.user_id
            except AttributeError:
                pass

        try:
            confirmed = await confirm_uc.execute(draft_dict, session_id, user_id)
        except DomainError as exc:
            return {"status": "error", "message": str(exc)}

        tool_context.state["transfer_draft"] = confirmed.to_state_dict()
        return {
            "status": "confirmed",
            "confirmation_code": confirmed.confirmation_code,
            "transfer_id": confirmed.id,
        }

    # ── Tool 4: list supported countries ────────────────────

    async def get_supported_countries(tool_context) -> dict:
        """Return the list of supported destination countries."""
        countries = await corridors_uc.get_supported_countries()
        return {"supported_countries": countries}

    # ── Tool 5: list delivery methods for a country ─────────

    async def get_delivery_methods(country_code: str, tool_context) -> dict:
        """Return the delivery methods available for a destination country.

        Args:
            country_code: ISO 3166-1 alpha-2 country code (e.g. "MX").
        """
        methods = await corridors_uc.get_delivery_methods(country_code)
        return {"country": country_code.upper(), "delivery_methods": methods}

    return [
        update_transfer_field,
        validate_transfer,
        confirm_transfer,
        get_supported_countries,
        get_delivery_methods,
    ]
