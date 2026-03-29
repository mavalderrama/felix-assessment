"""GetBalanceUseCase — retrieve the current account balance."""
from __future__ import annotations

from send_money.domain.entities import UserAccount
from send_money.domain.errors import DomainError
from send_money.domain.repositories import UserAccountRepository


class GetBalanceUseCase:
    def __init__(self, user_repo: UserAccountRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, user_id: str) -> UserAccount:
        """Return the account. Raises DomainError if the account is not found."""
        account = await self._user_repo.get_by_id(user_id)
        if account is None:
            raise DomainError(f"Account '{user_id}' not found.")
        return account
