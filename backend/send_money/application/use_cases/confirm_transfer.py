"""ConfirmTransferUseCase — persist a validated transfer and return a code."""
from __future__ import annotations

import uuid
from typing import Optional

from send_money.domain.entities import TransferDraft
from send_money.domain.enums import TransferStatus
from send_money.domain.errors import InvalidFieldError
from send_money.domain.repositories import AuditLogRepository, TransferRepository, UserAccountRepository
from send_money.domain.value_objects import Money


def _generate_confirmation_code() -> str:
    """Generate a short, human-readable confirmation code."""
    return f"SM-{uuid.uuid4().hex[:6].upper()}"


class ConfirmTransferUseCase:
    def __init__(
        self,
        transfer_repository: TransferRepository,
        audit_log_repository: Optional[AuditLogRepository] = None,
        user_account_repository: Optional[UserAccountRepository] = None,
    ) -> None:
        self._repository = transfer_repository
        self._audit = audit_log_repository
        self._user_repo = user_account_repository

    async def execute(
        self,
        draft_dict: dict,
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
        draft.idempotency_key = f"{session_id}:{draft.destination_country}:{draft.amount_units}:{draft.beneficiary_name}"
        draft.confirmation_code = _generate_confirmation_code()
        draft.session_id = session_id
        draft.user_id = user_id
        draft.status = TransferStatus.CONFIRMED

        # If the user has an account, deduct amount + fee atomically with the transfer save
        has_account = False
        if self._user_repo is not None and user_id:
            account = await self._user_repo.get_by_id(user_id)
            has_account = account is not None

        if has_account:
            amount = Money(
                units=draft.amount_units or 0,
                nanos=draft.amount_nanos or 0,
                currency_code=draft.amount_currency or "USD",
            )
            fee = Money(
                units=draft.fee_units or 0,
                nanos=draft.fee_nanos or 0,
                currency_code=draft.amount_currency or "USD",
            )
            total = Money.from_decimal(amount.to_decimal() + fee.to_decimal(), draft.amount_currency or "USD")
            saved = await self._repository.save_and_deduct(draft, user_id, total.units, total.nanos)
        else:
            saved = await self._repository.save(draft)

        if self._audit is not None:
            await self._audit.log(
                transfer_id=saved.id,
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
