"""LoginUseCase — authenticate an existing user account."""
from __future__ import annotations

from send_money.domain.auth import verify_password
from send_money.domain.entities import UserAccount
from send_money.domain.errors import AuthenticationError
from send_money.domain.repositories import UserAccountRepository


class LoginUseCase:
    def __init__(self, user_repo: UserAccountRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, username: str, password: str) -> UserAccount:
        """Authenticate and return the account. Raises AuthenticationError on failure."""
        account = await self._user_repo.get_by_username(username.strip())
        if account is None or not verify_password(password, account.password_hash):
            raise AuthenticationError()
        return account
