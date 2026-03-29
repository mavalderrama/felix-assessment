"""Unit tests for account-related use cases: CreateAccount, Login, AddFunds, GetBalance."""
from __future__ import annotations

from decimal import Decimal

import pytest

from send_money.domain.entities import UserAccount
from send_money.domain.errors import (
    AuthenticationError,
    DomainError,
    InsufficientFundsError,
    InvalidFieldError,
    UsernameAlreadyExistsError,
)
from send_money.domain.repositories import UserAccountRepository
from send_money.domain.value_objects import Money
from send_money.application.use_cases.add_funds import AddFundsUseCase
from send_money.application.use_cases.create_account import CreateAccountUseCase
from send_money.application.use_cases.get_balance import GetBalanceUseCase
from send_money.application.use_cases.login import LoginUseCase


# ── In-memory fake ────────────────────────────────────────────────────────────

class InMemoryUserAccountRepository(UserAccountRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, UserAccount] = {}
        self._by_username: dict[str, str] = {}  # username → id

    async def create(self, account: UserAccount) -> UserAccount:
        if account.username in self._by_username:
            raise UsernameAlreadyExistsError(account.username)
        self._by_id[account.id] = account
        self._by_username[account.username] = account.id
        return account

    async def get_by_username(self, username: str) -> UserAccount | None:
        uid = self._by_username.get(username)
        return self._by_id.get(uid) if uid else None

    async def get_by_id(self, user_id: str) -> UserAccount | None:
        return self._by_id.get(user_id)

    async def add_funds(self, user_id: str, units: int, nanos: int) -> UserAccount:
        account = self._by_id[user_id]
        current = Money(units=account.balance_units, nanos=account.balance_nanos, currency_code="")
        delta = Money(units=units, nanos=nanos, currency_code="")
        new_balance = Money.from_decimal(current.to_decimal() + delta.to_decimal(), account.balance_currency)
        updated = account.model_copy(update={"balance_units": new_balance.units, "balance_nanos": new_balance.nanos})
        self._by_id[user_id] = updated
        return updated

    async def deduct_funds(self, user_id: str, units: int, nanos: int) -> UserAccount:
        account = self._by_id[user_id]
        current = Money(units=account.balance_units, nanos=account.balance_nanos, currency_code="")
        delta = Money(units=units, nanos=nanos, currency_code="")
        if current.to_decimal() < delta.to_decimal():
            raise InsufficientFundsError(str(delta.to_decimal()), str(current.to_decimal()))
        new_balance = Money.from_decimal(current.to_decimal() - delta.to_decimal(), account.balance_currency)
        updated = account.model_copy(update={"balance_units": new_balance.units, "balance_nanos": new_balance.nanos})
        self._by_id[user_id] = updated
        return updated


@pytest.fixture
def repo():
    return InMemoryUserAccountRepository()


# ── CreateAccountUseCase ──────────────────────────────────────────────────────

class TestCreateAccountUseCase:
    @pytest.fixture
    def uc(self, repo):
        return CreateAccountUseCase(repo)

    @pytest.mark.asyncio
    async def test_creates_account_and_returns_it(self, uc):
        account = await uc.execute("alice", "secret123")
        assert account.username == "alice"
        assert account.id is not None

    @pytest.mark.asyncio
    async def test_password_is_hashed_not_stored_plaintext(self, uc):
        account = await uc.execute("bob", "my-password")
        assert account.password_hash != "my-password"
        assert "$" in account.password_hash  # salt$hash format

    @pytest.mark.asyncio
    async def test_duplicate_username_raises(self, uc):
        await uc.execute("carol", "pass1")
        with pytest.raises(UsernameAlreadyExistsError) as exc_info:
            await uc.execute("carol", "pass2")
        assert "carol" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_username_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute("", "password")

    @pytest.mark.asyncio
    async def test_whitespace_username_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute("   ", "password")

    @pytest.mark.asyncio
    async def test_default_balance_is_zero(self, uc, repo):
        account = await uc.execute("dave", "pass")
        stored = await repo.get_by_id(account.id)
        assert stored.balance_units == 0
        assert stored.balance_nanos == 0

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_username(self, uc):
        account = await uc.execute("  eve  ", "pass")
        assert account.username == "eve"


# ── LoginUseCase ──────────────────────────────────────────────────────────────

class TestLoginUseCase:
    @pytest.fixture
    def uc(self, repo):
        return LoginUseCase(repo)

    @pytest.fixture
    async def existing_account(self, repo):
        create_uc = CreateAccountUseCase(repo)
        return await create_uc.execute("frank", "correct-password")

    @pytest.mark.asyncio
    async def test_login_returns_account(self, uc, existing_account):
        account = await uc.execute("frank", "correct-password")
        assert account.username == "frank"
        assert account.id == existing_account.id

    @pytest.mark.asyncio
    async def test_wrong_password_raises_authentication_error(self, uc, existing_account):
        with pytest.raises(AuthenticationError):
            await uc.execute("frank", "wrong-password")

    @pytest.mark.asyncio
    async def test_nonexistent_user_raises_authentication_error(self, uc):
        with pytest.raises(AuthenticationError):
            await uc.execute("nobody", "any-password")

    @pytest.mark.asyncio
    async def test_empty_username_raises_authentication_error(self, uc):
        with pytest.raises(AuthenticationError):
            await uc.execute("", "password")


# ── AddFundsUseCase ───────────────────────────────────────────────────────────

class TestAddFundsUseCase:
    @pytest.fixture
    def uc(self, repo):
        return AddFundsUseCase(repo)

    @pytest.fixture
    async def account_id(self, repo):
        create_uc = CreateAccountUseCase(repo)
        account = await create_uc.execute("grace", "pass")
        return account.id

    @pytest.mark.asyncio
    async def test_adds_funds_increases_balance(self, uc, repo, account_id):
        updated = await uc.execute(account_id, "500", "USD")
        balance = Money(units=updated.balance_units, nanos=updated.balance_nanos, currency_code="USD")
        assert balance.to_decimal() == Decimal("500")

    @pytest.mark.asyncio
    async def test_adds_fractional_funds(self, uc, repo, account_id):
        updated = await uc.execute(account_id, "99.99", "USD")
        balance = Money(units=updated.balance_units, nanos=updated.balance_nanos, currency_code="USD")
        assert balance.to_decimal() == Decimal("99.99")

    @pytest.mark.asyncio
    async def test_add_zero_raises(self, uc, account_id):
        with pytest.raises(InvalidFieldError):
            await uc.execute(account_id, "0", "USD")

    @pytest.mark.asyncio
    async def test_add_negative_raises(self, uc, account_id):
        with pytest.raises(InvalidFieldError):
            await uc.execute(account_id, "-100", "USD")

    @pytest.mark.asyncio
    async def test_add_non_numeric_raises(self, uc, account_id):
        with pytest.raises(InvalidFieldError):
            await uc.execute(account_id, "abc", "USD")

    @pytest.mark.asyncio
    async def test_add_funds_twice_accumulates(self, uc, repo, account_id):
        await uc.execute(account_id, "100", "USD")
        updated = await uc.execute(account_id, "200", "USD")
        balance = Money(units=updated.balance_units, nanos=updated.balance_nanos, currency_code="USD")
        assert balance.to_decimal() == Decimal("300")


# ── GetBalanceUseCase ─────────────────────────────────────────────────────────

class TestGetBalanceUseCase:
    @pytest.fixture
    def uc(self, repo):
        return GetBalanceUseCase(repo)

    @pytest.fixture
    async def account_id(self, repo):
        create_uc = CreateAccountUseCase(repo)
        account = await create_uc.execute("henry", "pass")
        return account.id

    @pytest.mark.asyncio
    async def test_returns_account(self, uc, account_id):
        account = await uc.execute(account_id)
        assert account.username == "henry"

    @pytest.mark.asyncio
    async def test_initial_balance_is_zero(self, uc, account_id):
        account = await uc.execute(account_id)
        assert account.balance_units == 0
        assert account.balance_nanos == 0

    @pytest.mark.asyncio
    async def test_nonexistent_user_raises(self, uc):
        with pytest.raises(DomainError):
            await uc.execute("does-not-exist")
