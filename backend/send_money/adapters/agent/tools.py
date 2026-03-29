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
    add_funds_uc = container.add_funds_uc
    get_balance_uc = container.get_balance_uc
    create_account_uc = container.create_account_uc
    login_uc = container.login_uc
    list_beneficiaries_uc = container.list_beneficiaries_uc
    save_beneficiary_uc = container.save_beneficiary_uc

    def _get_user_id(tool_context) -> str:
        """Check session state first (set by auth tools in web mode),
        fall back to session-level user_id (set by CLI)."""
        uid = tool_context.state.get("user_id", "")
        if uid:
            return uid
        try:
            return tool_context.invocation_context.session.user_id or ""
        except AttributeError:
            return ""

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
                amount, currency, beneficiary_name, beneficiary_account,
                delivery_method.
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

        # Auto-save beneficiary as soon as both name and account are set
        if field_name in ("beneficiary_name", "beneficiary_account"):
            uid = _get_user_id(tool_context)
            if uid and updated.beneficiary_name and updated.beneficiary_account:
                try:
                    await save_beneficiary_uc.execute(
                        user_id=uid,
                        name=updated.beneficiary_name,
                        account_number=updated.beneficiary_account,
                        country_code=updated.destination_country or "",
                        delivery_method=str(updated.delivery_method or ""),
                    )
                except Exception:
                    pass

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
        from send_money.domain.enums import format_country, format_currency, format_delivery_method
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
            "destination_country": format_country(validated.destination_country or ""),
            "destination_currency": format_currency(validated.destination_currency or ""),
            "receive_amount": str(receive),
            "beneficiary_name": validated.beneficiary_name,
            "delivery_method": format_delivery_method(str(validated.delivery_method)),
        }

    # ── Tool 3: confirm and persist ─────────────────────────

    async def confirm_transfer(tool_context) -> dict:
        """Confirm and persist the transfer.  Call only after user explicitly agrees.

        Returns the confirmation code.
        """
        from send_money.domain.errors import DomainError

        draft_dict: dict = tool_context.state.get("transfer_draft", {})

        # user_id: check state first (set by auth tools), fall back to session
        user_id: str = _get_user_id(tool_context)

        # session_id
        session_id: str = ""
        try:
            session_id = tool_context.invocation_context.session.id or ""
        except AttributeError:
            pass

        langfuse_trace_id: str = tool_context.state.get("_langfuse_trace_id", "") or ""
        langfuse_observation_id: str = tool_context.state.get("_langfuse_observation_id", "") or ""

        try:
            confirmed = await confirm_uc.execute(
                draft_dict,
                session_id,
                user_id,
                langfuse_trace_id=langfuse_trace_id,
                langfuse_observation_id=langfuse_observation_id,
            )
        except DomainError as exc:
            return {"status": "error", "message": str(exc)}

        # Auto-save beneficiary for future use (best-effort).
        # Read beneficiary_account from the original draft_dict because the
        # TransferRecord (and thus confirmed) does not persist that field.
        auto_save_user_id = _get_user_id(tool_context)
        beneficiary_account = draft_dict.get("beneficiary_account") or ""
        if auto_save_user_id and confirmed.beneficiary_name and beneficiary_account:
            try:
                saved_beneficiary = await save_beneficiary_uc.execute(
                    user_id=auto_save_user_id,
                    name=confirmed.beneficiary_name,
                    account_number=beneficiary_account,
                    country_code=confirmed.destination_country or "",
                    delivery_method=str(confirmed.delivery_method or ""),
                )
                confirmed.beneficiary_id = saved_beneficiary.id
            except Exception:
                pass  # Never fail the transfer due to beneficiary save errors

        tool_context.state["transfer_draft"] = confirmed.to_state_dict()
        return {
            "status": "confirmed",
            "confirmation_code": confirmed.confirmation_code,
            "transfer_id": confirmed.id,
        }

    # ── Tool 4: list supported countries ────────────────────

    async def get_supported_countries(tool_context) -> dict:
        """Return the list of supported destination countries."""
        from send_money.domain.enums import format_country
        countries = await corridors_uc.get_supported_countries()
        return {"supported_countries": [format_country(c) for c in countries]}

    # ── Tool 5: list delivery methods for a country ─────────

    async def get_delivery_methods(country_code: str, tool_context) -> dict:
        """Return the delivery methods available for a destination country.

        Args:
            country_code: ISO 3166-1 alpha-2 country code (e.g. "MX").
        """
        from send_money.domain.enums import format_country, format_delivery_method
        methods = await corridors_uc.get_delivery_methods(country_code)
        return {
            "country": format_country(country_code.upper()),
            "delivery_methods": [format_delivery_method(m) for m in methods],
        }

    # ── Tool 6: add funds to account ────────────────────────

    async def add_funds(amount: str, currency: str, tool_context) -> dict:
        """Add funds to the user's account balance.

        Args:
            amount: The amount to deposit (e.g. "500", "100.50").
            currency: ISO 4217 currency code (e.g. "USD").
        """
        from send_money.domain.errors import DomainError
        from send_money.domain.value_objects import Money

        user_id = _get_user_id(tool_context)
        if not user_id:
            return {"status": "error", "message": "No authenticated user found."}
        try:
            account = await add_funds_uc.execute(user_id, amount, currency)
        except DomainError as exc:
            return {"status": "error", "message": str(exc)}

        balance = Money(
            units=account.balance_units,
            nanos=account.balance_nanos,
            currency_code=account.balance_currency,
        )
        return {"status": "funds_added", "new_balance": str(balance)}

    # ── Tool 7: get account balance ──────────────────────────

    async def get_balance(tool_context) -> dict:
        """Return the current account balance."""
        from send_money.domain.errors import DomainError
        from send_money.domain.value_objects import Money

        user_id = _get_user_id(tool_context)
        if not user_id:
            return {"status": "error", "message": "No authenticated user found."}
        try:
            account = await get_balance_uc.execute(user_id)
        except DomainError as exc:
            return {"status": "error", "message": str(exc)}

        balance = Money(
            units=account.balance_units,
            nanos=account.balance_nanos,
            currency_code=account.balance_currency,
        )
        return {"status": "ok", "balance": str(balance), "currency": account.balance_currency}

    # ── Tool 8: list saved beneficiaries ─────────────────────

    async def get_saved_beneficiaries(tool_context) -> dict:
        """Return the list of saved beneficiaries for the current user.

        Call this at the start of a transfer to check if the user has
        previously saved recipients.  If the user mentions a name that
        matches, pre-fill beneficiary_name, beneficiary_account, and
        optionally destination_country and delivery_method.
        """
        user_id = _get_user_id(tool_context)
        if not user_id:
            return {"status": "error", "message": "No authenticated user found."}
        beneficiaries = await list_beneficiaries_uc.execute(user_id)
        return {
            "status": "ok",
            "beneficiaries": [
                {
                    "id": b.id,
                    "name": b.name,
                    "account_number": b.account_number,
                    "country_code": b.country_code or "",
                    "delivery_method": str(b.delivery_method) if b.delivery_method else "",
                }
                for b in beneficiaries
            ],
        }

    # ── Tool 9: create a new account ─────────────────────────

    async def create_account(username: str, password: str, tool_context) -> dict:
        """Create a new user account.

        Args:
            username: Desired username (2-128 characters).
            password: Password for the account (minimum 4 characters).
        """
        from send_money.domain.errors import DomainError

        try:
            account = await create_account_uc.execute(username, password)
        except DomainError as exc:
            return {"status": "error", "message": str(exc)}

        tool_context.state["user_id"] = account.id
        tool_context.state["username"] = account.username
        return {"status": "account_created", "username": account.username}

    # ── Tool 10: log in to an existing account ───────────────

    async def login(username: str, password: str, tool_context) -> dict:
        """Log in to an existing user account.

        Args:
            username: The account username.
            password: The account password.
        """
        from send_money.domain.errors import DomainError

        try:
            account = await login_uc.execute(username, password)
        except DomainError as exc:
            return {"status": "error", "message": str(exc)}

        tool_context.state["user_id"] = account.id
        tool_context.state["username"] = account.username
        return {"status": "logged_in", "username": account.username}

    return [
        update_transfer_field,
        validate_transfer,
        confirm_transfer,
        get_supported_countries,
        get_delivery_methods,
        get_saved_beneficiaries,
        add_funds,
        get_balance,
        create_account,
        login,
    ]
