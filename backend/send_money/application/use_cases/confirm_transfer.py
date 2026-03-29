"""ConfirmTransferUseCase — persist a validated transfer and return a code."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from send_money.application.ports import ExchangeRateService
from send_money.domain.entities import TransferDraft
from send_money.domain.enums import TransferStatus
from send_money.domain.errors import InvalidFieldError
from send_money.domain.repositories import (
    AuditLogRepository,
    TransferRepository,
    UserAccountRepository,
)
from send_money.domain.value_objects import Money

logger = logging.getLogger(__name__)


def _generate_confirmation_code() -> str:
    """Generate a short, human-readable confirmation code."""
    return f"SM-{uuid.uuid4().hex[:6].upper()}"


class ConfirmTransferUseCase:
    def __init__(
        self,
        transfer_repository: TransferRepository,
        audit_log_repository: AuditLogRepository | None = None,
        user_account_repository: UserAccountRepository | None = None,
        exchange_rate_service: ExchangeRateService | None = None,
    ) -> None:
        self._repository = transfer_repository
        self._audit = audit_log_repository
        self._user_repo = user_account_repository
        self._fx = exchange_rate_service

    async def execute(
        self,
        draft_dict: dict[str, Any],
        session_id: str,
        user_id: str,
        langfuse_trace_id: str = "",
        langfuse_observation_id: str = "",
    ) -> TransferDraft:
        """Persist the transfer, write an audit log entry, and return the draft."""
        draft = TransferDraft.from_state_dict(draft_dict)

        if draft.status != TransferStatus.VALIDATED:
            raise InvalidFieldError(
                "transfer",
                "Transfer must be validated before confirmation.",
            )

        draft.id = str(uuid.uuid4())
        draft.idempotency_key = (
            f"{session_id}:{draft.destination_country}"
            f":{draft.amount_units}:{draft.beneficiary_name}"
        )
        draft.confirmation_code = _generate_confirmation_code()
        draft.session_id = session_id
        draft.user_id = user_id
        draft.status = TransferStatus.CONFIRMED

        # If the user has an account, deduct amount + fee atomically with the
        # transfer save
        account = None
        if self._user_repo is not None and user_id:
            account = await self._user_repo.get_by_id(user_id)
            if account is None:
                logger.warning(
                    "confirm_transfer: user_id=%r found no matching account", user_id
                )
        elif not user_id:
            logger.debug(
                "confirm_transfer: no user_id provided — skipping balance deduction"
            )

        if account is not None:
            send_currency = draft.amount_currency or "USD"
            amount = Money(
                units=draft.amount_units or 0,
                nanos=draft.amount_nanos or 0,
                currency_code=send_currency,
            )
            fee = Money(
                units=draft.fee_units or 0,
                nanos=draft.fee_nanos or 0,
                currency_code=send_currency,
            )
            total_send = Money.from_decimal(
                amount.to_decimal() + fee.to_decimal(), send_currency
            )

            # Convert total to account currency when they differ
            if account.balance_currency != send_currency and self._fx is not None:
                rate = await self._fx.get_rate(send_currency, account.balance_currency)
                total = Money.from_decimal(
                    total_send.to_decimal() * rate, account.balance_currency
                )
            else:
                total = total_send

            saved = await self._repository.save_and_deduct(
                draft, user_id, total.units, total.nanos
            )
        else:
            saved = await self._repository.save(draft)

        if self._audit is not None:
            await self._audit.log(
                transfer_id=saved.id or "",
                session_id=session_id,
                user_id=user_id,
                action="CONFIRMED",
                langfuse_trace_id=langfuse_trace_id,
                langfuse_observation_id=langfuse_observation_id,
                metadata={
                    "destination_country": saved.destination_country,
                    "amount_currency": saved.amount_currency,
                    "confirmation_code": saved.confirmation_code,
                },
            )

        return saved
