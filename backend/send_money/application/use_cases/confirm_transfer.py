"""ConfirmTransferUseCase — persist a validated transfer and return a code."""
from __future__ import annotations

import uuid

from send_money.domain.entities import TransferDraft
from send_money.domain.enums import TransferStatus
from send_money.domain.errors import InvalidFieldError
from send_money.domain.repositories import TransferRepository


def _generate_confirmation_code() -> str:
    """Generate a short, human-readable confirmation code."""
    return f"SM-{uuid.uuid4().hex[:6].upper()}"


class ConfirmTransferUseCase:
    def __init__(self, transfer_repository: TransferRepository) -> None:
        self._repository = transfer_repository

    async def execute(self, draft_dict: dict, session_id: str, user_id: str) -> TransferDraft:
        """Persist the transfer and return the draft with a confirmation code."""
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

        return await self._repository.save(draft)
