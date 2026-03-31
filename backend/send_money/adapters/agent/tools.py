"""ADK tool functions for the Send Money Agent.

Tools are created via a closure factory so use-case dependencies are captured
at construction time — no global state, fully testable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from send_money.infrastructure.container import Container

logger = logging.getLogger(__name__)

_TD = "td:"


def _read_draft(state: Any) -> dict[str, Any]:
    """Reconstruct transfer draft from per-field state keys (td:<field>).

    Each field is stored as a separate state key so that parallel tool calls
    writing to different fields don't overwrite each other (ADK tracks state
    deltas at the key level — last writer wins per key).

    Falls back to the legacy ``state["transfer_draft"]`` dict for sessions
    created before this change.

    If the draft status is CONFIRMED, returns an empty dict so the next
    transfer starts fresh — the completed transfer is already persisted in
    the database.
    """
    from send_money.domain.entities import TransferDraft

    draft: dict[str, Any] = {}
    has_td = False
    for field in TransferDraft.model_fields:
        if field == "REQUIRED_FIELDS":
            continue
        key = f"{_TD}{field}"
        if key in state:
            draft[field] = state[key]
            has_td = True

    d = draft if has_td else dict(state.get("transfer_draft", {}))

    # A CONFIRMED draft belongs to a completed transfer — start fresh.
    if d.get("status") == "CONFIRMED":
        return {}
    return d


def _write_draft(state: Any, draft: Any, before: dict[str, Any] | None = None) -> None:
    """Persist draft by writing each field as its own state key (td:<field>).

    Writing to separate keys means concurrent tool calls for different fields
    accumulate correctly instead of one overwriting the other.  The full dict
    is also written to ``state["transfer_draft"]`` as a convenience copy for
    the instruction builder and observability layer.

    When ``before`` is supplied only fields whose value differs from ``before``
    are written.  This prevents a parallel tool call from overwriting a field
    it never touched (e.g. Tool A sets beneficiary_name; Tool B sets
    beneficiary_account — without ``before``, Tool B would also write
    ``td:beneficiary_name = None``, clobbering Tool A's write).
    """
    d = draft.to_state_dict()
    for field, value in d.items():
        if before is None or before.get(field) != value:
            state[f"{_TD}{field}"] = value
    state["transfer_draft"] = d


def create_tools(container: Container) -> list[Callable[..., Any]]:
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

    def _get_user_id(tool_context: Any) -> str:
        """Check session state first (set by auth tools in web mode),
        fall back to session-level user_id (set by CLI)."""
        uid = tool_context.state.get("user_id", "")
        if uid:
            return str(uid)
        try:
            return str(tool_context.invocation_context.session.user_id or "")
        except AttributeError:
            return ""

    # ── Tool 1: update a single field ───────────────────────

    async def update_transfer_field(
        field_name: str,
        field_value: str,
        tool_context: Any,
    ) -> dict[str, Any]:
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

        draft_dict: dict[str, Any] = _read_draft(tool_context.state)
        before = dict(draft_dict)
        try:
            updated = await collect_uc.execute(draft_dict, field_name, field_value)
        except DomainError as exc:
            return {"status": "error", "field": field_name, "message": str(exc)}

        _write_draft(tool_context.state, updated, before=before)

        # Auto-save beneficiary once ALL key fields are present: name, account,
        # delivery_method, AND destination_country.  Requiring all four prevents
        # saving with stale data (e.g. delivery_method pre-filled by
        # select_beneficiary before the user overrides it).
        _BENEFICIARY_TRIGGER_FIELDS = {
            "beneficiary_name",
            "beneficiary_account",
            "delivery_method",
            "destination_country",
        }
        if field_name in _BENEFICIARY_TRIGGER_FIELDS:
            uid = _get_user_id(tool_context)
            if (
                uid
                and updated.beneficiary_name
                and updated.beneficiary_account
                and updated.delivery_method
                and updated.destination_country
            ):
                try:
                    await save_beneficiary_uc.execute(
                        user_id=uid,
                        name=updated.beneficiary_name,
                        account_number=updated.beneficiary_account,
                        country_code=updated.destination_country,
                        delivery_method=str(updated.delivery_method),
                    )
                except Exception:
                    logger.exception(
                        "Auto-save beneficiary failed during update_transfer_field "
                        "(user=%r name=%r account=%r country=%r method=%r)",
                        uid,
                        updated.beneficiary_name,
                        updated.beneficiary_account,
                        updated.destination_country,
                        str(updated.delivery_method),
                    )

        return {
            "status": "updated",
            "field": field_name,
            "value": field_value,
            "missing_fields": updated.missing_fields,
        }

    # ── Tool 2: validate the complete draft ─────────────────

    async def validate_transfer(tool_context: Any) -> dict[str, Any]:
        """Validate the transfer draft and calculate fees and exchange rates.

        Call this once all required fields are set.  Returns a summary dict
        with the calculated fee and receive amount.
        """
        from send_money.domain.enums import (
            format_country,
            format_currency,
            format_delivery_method,
        )
        from send_money.domain.errors import DomainError
        from send_money.domain.value_objects import Money

        draft_dict: dict[str, Any] = _read_draft(tool_context.state)
        try:
            validated = await validate_uc.execute(draft_dict)
        except DomainError as exc:
            return {"status": "error", "message": str(exc)}

        _write_draft(tool_context.state, validated)

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
            "destination_currency": format_currency(
                validated.destination_currency or ""
            ),
            "receive_amount": str(receive),
            "beneficiary_name": validated.beneficiary_name,
            "delivery_method": format_delivery_method(str(validated.delivery_method)),
        }

    # ── Tool 3: confirm and persist ─────────────────────────

    async def confirm_transfer(tool_context: Any) -> dict[str, Any]:
        """Confirm and persist the transfer.  Call only after user explicitly agrees.

        Returns the confirmation code.
        """
        from send_money.domain.errors import DomainError

        draft_dict: dict[str, Any] = _read_draft(tool_context.state)

        # user_id: check state first (set by auth tools), fall back to session
        user_id: str = _get_user_id(tool_context)

        # session_id
        session_id: str = ""
        try:
            session_id = tool_context.invocation_context.session.id or ""
        except AttributeError:
            pass

        langfuse_trace_id: str = tool_context.state.get("_langfuse_trace_id", "") or ""
        langfuse_observation_id: str = (
            tool_context.state.get("_langfuse_observation_id", "") or ""
        )

        # Auto-save beneficiary BEFORE persisting the transfer so that
        # beneficiary_id is included in the TransferRecord from the start.
        beneficiary_account = draft_dict.get("beneficiary_account") or ""
        beneficiary_name = draft_dict.get("beneficiary_name") or ""
        if user_id and beneficiary_name and beneficiary_account:
            try:
                saved_beneficiary = await save_beneficiary_uc.execute(
                    user_id=user_id,
                    name=beneficiary_name,
                    account_number=beneficiary_account,
                    country_code=draft_dict.get("destination_country") or "",
                    delivery_method=draft_dict.get("delivery_method") or "",
                )
                draft_dict["beneficiary_id"] = saved_beneficiary.id
            except Exception:
                logger.exception(
                    "Auto-save beneficiary failed during confirm_transfer "
                    "(user=%r name=%r account=%r country=%r method=%r)",
                    user_id,
                    beneficiary_name,
                    beneficiary_account,
                    draft_dict.get("destination_country"),
                    draft_dict.get("delivery_method"),
                )
                # Never fail the transfer due to beneficiary save errors

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

        _write_draft(tool_context.state, confirmed)

        # Reset the session draft so the next transfer starts with a blank slate.
        # The completed transfer is persisted in the database; the in-memory draft
        # is no longer needed and must not bleed into a subsequent transfer.
        from send_money.domain.entities import TransferDraft as _TD_cls

        _write_draft(tool_context.state, _TD_cls())

        return {
            "status": "confirmed",
            "confirmation_code": confirmed.confirmation_code,
            "transfer_id": confirmed.id,
        }

    # ── Tool 4: list supported countries ────────────────────

    async def get_supported_countries(tool_context: Any) -> dict[str, Any]:
        """Return the list of supported destination countries."""
        from send_money.domain.enums import format_country

        countries = await corridors_uc.get_supported_countries()
        return {"supported_countries": [format_country(c) for c in countries]}

    # ── Tool 5: list delivery methods for a country ─────────

    async def get_delivery_methods(
        country_code: str, tool_context: Any
    ) -> dict[str, Any]:
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

    async def add_funds(
        amount: str, currency: str, tool_context: Any
    ) -> dict[str, Any]:
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

    async def get_balance(tool_context: Any) -> dict[str, Any]:
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
        return {
            "status": "ok",
            "balance": str(balance),
            "currency": account.balance_currency,
        }

    # ── Tool 8: list saved beneficiaries ─────────────────────

    async def get_saved_beneficiaries(tool_context: Any) -> dict[str, Any]:
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
                    "delivery_method": str(b.delivery_method)
                    if b.delivery_method
                    else "",
                }
                for b in beneficiaries
            ],
        }

    # ── Tool 9: select a saved beneficiary ─────────────────────

    async def select_beneficiary(
        beneficiary_name: str, tool_context: Any
    ) -> dict[str, Any]:
        """Pre-fill transfer fields from a saved beneficiary.

        Call this when the user mentions a recipient name that matches a saved
        beneficiary.  Sets beneficiary_name, beneficiary_account, and — if
        unambiguous — destination_country and delivery_method.

        If the beneficiary has multiple saved delivery methods, the tool
        returns status "multiple_found" with an "options" list.  In that case
        ask the user which delivery method to use, then call
        update_transfer_field() for "destination_country" and
        "delivery_method" with the chosen values.

        Args:
            beneficiary_name: The name of the saved beneficiary to select.
        """
        from send_money.domain.enums import format_country, format_delivery_method
        from send_money.domain.errors import DomainError

        user_id = _get_user_id(tool_context)
        if not user_id:
            return {"status": "error", "message": "No authenticated user found."}

        beneficiaries = await list_beneficiaries_uc.execute(user_id)
        name_lower = beneficiary_name.strip().lower()
        matches = [b for b in beneficiaries if b.name.lower() == name_lower]

        if not matches:
            return {"status": "not_found", "name": beneficiary_name}

        draft_dict: dict[str, Any] = _read_draft(tool_context.state)

        # Always set the name (the same across all entries)
        updated = await collect_uc.execute(
            draft_dict, "beneficiary_name", matches[0].name
        )
        draft_dict = updated.to_state_dict()

        # If the user already chose a country, narrow matches to that country.
        user_country = draft_dict.get("destination_country")
        if user_country and len(matches) > 1:
            country_matches = [m for m in matches if m.country_code == user_country]
            if country_matches:
                matches = country_matches
            else:
                # None of the saved entries match the user's country.
                _write_draft(tool_context.state, updated)
                return {
                    "status": "country_conflict",
                    "beneficiary_name": matches[0].name,
                    "saved_country": ", ".join(m.country_code or "?" for m in matches),
                    "user_country": user_country,
                    "message": (
                        f"No saved entry for {matches[0].name} in "
                        f"{format_country(user_country or '')}. "
                        f"Ask the user for the account number for "
                        f"{format_country(user_country or '')}."
                    ),
                    "missing_fields": updated.missing_fields,
                }

        if len(matches) == 1:
            # Single entry — apply fields that don't conflict with user-set values.
            match = matches[0]
            user_country = draft_dict.get("destination_country")

            # Country conflict: user already chose a different country.
            # The saved account number and delivery method belong to a different
            # country and must NOT be applied — they would be wrong for the
            # user's chosen destination.
            country_conflict = (
                user_country
                and match.country_code
                and user_country != match.country_code
            )
            if country_conflict:
                _write_draft(tool_context.state, updated)
                return {
                    "status": "country_conflict",
                    "beneficiary_name": match.name,
                    "saved_country": match.country_code,
                    "user_country": user_country,
                    "message": (
                        f"Saved entry for {match.name} is for "
                        f"{format_country(match.country_code or '')}, but the user "
                        f"chose {format_country(user_country or '')}. "
                        f"Ask the user for the account number for "
                        f"{format_country(user_country or '')}."
                    ),
                    "missing_fields": updated.missing_fields,
                }

            # No conflict — apply available fields only if not already set.
            # Skip the saved account when the user chose a different delivery
            # method — different methods use different identifiers (bank
            # account vs. phone number vs. pickup code).
            user_delivery = draft_dict.get("delivery_method")
            delivery_changed = (
                user_delivery
                and match.delivery_method
                and user_delivery != str(match.delivery_method)
            )
            if (
                match.account_number
                and not draft_dict.get("beneficiary_account")
                and not delivery_changed
            ):
                updated = await collect_uc.execute(
                    draft_dict, "beneficiary_account", match.account_number
                )
                draft_dict = updated.to_state_dict()
            if match.country_code and not draft_dict.get("destination_country"):
                try:
                    updated = await collect_uc.execute(
                        draft_dict, "destination_country", match.country_code
                    )
                    draft_dict = updated.to_state_dict()
                except DomainError:
                    pass
            if match.delivery_method and not draft_dict.get("delivery_method"):
                try:
                    updated = await collect_uc.execute(
                        draft_dict, "delivery_method", str(match.delivery_method)
                    )
                    draft_dict = updated.to_state_dict()
                except DomainError:
                    pass

            _write_draft(tool_context.state, updated)
            return {
                "status": "selected",
                "beneficiary_name": match.name,
                "beneficiary_account": draft_dict.get("beneficiary_account") or "",
                "destination_country": draft_dict.get("destination_country")
                or match.country_code
                or "",
                "delivery_method": draft_dict.get("delivery_method")
                or (str(match.delivery_method) if match.delivery_method else ""),
                "missing_fields": updated.missing_fields,
            }

        # Multiple entries — pre-fill only fields shared by all matches.
        # Leave ambiguous fields for the agent to present and collect from the user.
        accounts = {m.account_number for m in matches}
        if len(accounts) == 1:
            updated = await collect_uc.execute(
                draft_dict, "beneficiary_account", matches[0].account_number
            )
            draft_dict = updated.to_state_dict()

        countries = {m.country_code for m in matches if m.country_code}
        if len(countries) == 1 and not draft_dict.get("destination_country"):
            try:
                updated = await collect_uc.execute(
                    draft_dict, "destination_country", countries.pop()
                )
                draft_dict = updated.to_state_dict()
            except DomainError:
                pass

        _write_draft(tool_context.state, updated)
        return {
            "status": "multiple_found",
            "beneficiary_name": matches[0].name,
            "options": [
                {
                    "account_number": m.account_number,
                    "country_code": m.country_code or "",
                    "country": format_country(m.country_code) if m.country_code else "",
                    "delivery_method": str(m.delivery_method)
                    if m.delivery_method
                    else "",
                    "delivery_method_display": format_delivery_method(
                        str(m.delivery_method)
                    )
                    if m.delivery_method
                    else "",
                }
                for m in matches
            ],
            "missing_fields": updated.missing_fields,
        }

    # ── Tool 10: create a new account ─────────────────────────

    async def create_account(
        username: str, password: str, tool_context: Any
    ) -> dict[str, Any]:
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

    # ── Tool 11: log in to an existing account ───────────────

    async def login(username: str, password: str, tool_context: Any) -> dict[str, Any]:
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
        select_beneficiary,
        add_funds,
        get_balance,
        create_account,
        login,
    ]
