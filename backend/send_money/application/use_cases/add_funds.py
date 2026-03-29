"""AddFundsUseCase — deposit money into a user account."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from send_money.domain.entities import UserAccount
from send_money.domain.errors import InvalidFieldError
from send_money.domain.repositories import UserAccountRepository
from send_money.domain.value_objects import Money


class AddFundsUseCase:
    def __init__(self, user_repo: UserAccountRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, user_id: str, amount_str: str, currency: str) -> UserAccount:
        """Add funds to the account. Returns the updated account."""
        try:
            amount = Decimal(amount_str.strip().replace(",", ""))
        except InvalidOperation:
            raise InvalidFieldError("amount", f"'{amount_str}' is not a valid number.")
        if amount <= 0:
            raise InvalidFieldError("amount", "Amount must be greater than zero.")

        money = Money.from_decimal(amount, currency.strip().upper())
        return await self._user_repo.add_funds(user_id, money.units, money.nanos)
