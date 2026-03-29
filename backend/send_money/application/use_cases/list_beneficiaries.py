"""ListBeneficiariesUseCase — retrieve saved recipients for a user."""
from __future__ import annotations

from send_money.domain.entities import Beneficiary
from send_money.domain.repositories import BeneficiaryRepository


class ListBeneficiariesUseCase:
    def __init__(self, beneficiary_repo: BeneficiaryRepository) -> None:
        self._repo = beneficiary_repo

    async def execute(self, user_id: str) -> list[Beneficiary]:
        """Return all saved beneficiaries for the given user, ordered by name."""
        return await self._repo.list_for_user(user_id)
