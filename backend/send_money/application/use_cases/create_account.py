"""CreateAccountUseCase — register a new user account."""
from __future__ import annotations

import uuid

from send_money.domain.auth import hash_password
from send_money.domain.entities import UserAccount
from send_money.domain.repositories import UserAccountRepository


class CreateAccountUseCase:
    def __init__(self, user_repo: UserAccountRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, username: str, password: str) -> UserAccount:
        """Create a new account. Raises UsernameAlreadyExistsError if taken."""
        username = username.strip()
        if not username:
            from send_money.domain.errors import InvalidFieldError
            raise InvalidFieldError("username", "Username cannot be empty.")

        account = UserAccount(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=hash_password(password),
        )
        return await self._user_repo.create(account)
