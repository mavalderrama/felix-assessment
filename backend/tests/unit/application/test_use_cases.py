"""Unit tests for application use cases."""
from __future__ import annotations

from decimal import Decimal

import pytest

from send_money.domain.entities import TransferDraft, UserAccount
from send_money.domain.enums import DeliveryMethod, TransferStatus
from send_money.domain.errors import (
    InsufficientFundsError,
    InvalidFieldError,
    UnsupportedCorridorError,
    UsernameAlreadyExistsError,
)
from send_money.domain.repositories import UserAccountRepository
from send_money.domain.value_objects import Money
from send_money.application.use_cases.collect_transfer_details import CollectTransferDetailsUseCase
from send_money.application.use_cases.validate_transfer import ValidateTransferUseCase
from send_money.application.use_cases.confirm_transfer import ConfirmTransferUseCase
from send_money.application.use_cases.get_corridors import GetCorridorsUseCase


# ── Helpers ──────────────────────────────────────────────────────────────────

def _draft_dict(**kwargs) -> dict:
    return TransferDraft(**kwargs).to_state_dict()


def _validated_draft_dict() -> dict:
    draft = TransferDraft(
        destination_country="MX",
        amount_units=500,
        amount_nanos=0,
        amount_currency="USD",
        beneficiary_name="Maria Garcia",
        beneficiary_account="1234567890",
        delivery_method=DeliveryMethod.BANK_DEPOSIT,
        status=TransferStatus.VALIDATED,
        source_currency="USD",
        destination_currency="MXN",
        fee_units=5,
        fee_nanos=0,
        receive_amount_units=9450,
        receive_amount_nanos=0,
    )
    return draft.to_state_dict()


# ── CollectTransferDetailsUseCase ────────────────────────────────────────────

class TestCollectTransferDetailsUseCase:
    @pytest.fixture
    def uc(self, in_memory_corridor_repo):
        return CollectTransferDetailsUseCase(in_memory_corridor_repo)

    @pytest.mark.asyncio
    async def test_set_destination_country(self, uc):
        draft = await uc.execute({}, "destination_country", "MX")
        assert draft.destination_country == "MX"

    @pytest.mark.asyncio
    async def test_set_destination_country_uppercase(self, uc):
        draft = await uc.execute({}, "destination_country", "mx")
        assert draft.destination_country == "MX"

    @pytest.mark.asyncio
    async def test_set_unsupported_country_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute({}, "destination_country", "ZZ")

    @pytest.mark.asyncio
    async def test_set_amount(self, uc):
        draft = await uc.execute({}, "amount", "150.50")
        assert draft.amount_units == 150
        assert draft.amount_nanos == 500_000_000

    @pytest.mark.asyncio
    async def test_set_amount_with_comma(self, uc):
        draft = await uc.execute({}, "amount", "1,000")
        assert draft.amount_units == 1000

    @pytest.mark.asyncio
    async def test_set_amount_negative_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute({}, "amount", "-50")

    @pytest.mark.asyncio
    async def test_set_amount_zero_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute({}, "amount", "0")

    @pytest.mark.asyncio
    async def test_set_amount_non_numeric_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute({}, "amount", "abc")

    @pytest.mark.asyncio
    async def test_set_currency(self, uc):
        draft = await uc.execute({}, "currency", "eur")
        assert draft.amount_currency == "EUR"
        assert draft.source_currency == "EUR"

    @pytest.mark.asyncio
    async def test_set_currency_invalid_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute({}, "currency", "USDD")

    @pytest.mark.asyncio
    async def test_set_beneficiary_name(self, uc):
        draft = await uc.execute({}, "beneficiary_name", "  John Doe  ")
        assert draft.beneficiary_name == "John Doe"

    @pytest.mark.asyncio
    async def test_set_beneficiary_name_too_short_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute({}, "beneficiary_name", "A")

    @pytest.mark.asyncio
    async def test_set_beneficiary_account(self, uc):
        draft = await uc.execute({}, "beneficiary_account", "  1234567890  ")
        assert draft.beneficiary_account == "1234567890"

    @pytest.mark.asyncio
    async def test_set_beneficiary_account_empty_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute({}, "beneficiary_account", "   ")

    @pytest.mark.asyncio
    async def test_set_delivery_method(self, uc):
        base = _draft_dict(destination_country="MX")
        draft = await uc.execute(base, "delivery_method", "BANK_DEPOSIT")
        assert draft.delivery_method == DeliveryMethod.BANK_DEPOSIT

    @pytest.mark.asyncio
    async def test_set_delivery_method_invalid_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute({}, "delivery_method", "CARRIER_PIGEON")

    @pytest.mark.asyncio
    async def test_unknown_field_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute({}, "eye_color", "blue")

    @pytest.mark.asyncio
    async def test_changing_country_resets_delivery_method(self, uc):
        base = _draft_dict(destination_country="MX", delivery_method=DeliveryMethod.BANK_DEPOSIT)
        draft = await uc.execute(base, "destination_country", "GT")
        assert draft.delivery_method is None

    @pytest.mark.asyncio
    async def test_changing_amount_resets_fee(self, uc):
        base = _draft_dict(fee_units=5, fee_nanos=0, receive_amount_units=100, receive_amount_nanos=0)
        draft = await uc.execute(base, "amount", "200")
        assert draft.fee_units is None
        assert draft.receive_amount_units is None


# ── ValidateTransferUseCase ───────────────────────────────────────────────────

class TestValidateTransferUseCase:
    @pytest.fixture
    def uc(self, in_memory_corridor_repo):
        from send_money.infrastructure.simulated_services import (
            SimulatedExchangeRateService,
            SimulatedFeeService,
        )
        return ValidateTransferUseCase(
            corridor_repository=in_memory_corridor_repo,
            exchange_rate_service=SimulatedExchangeRateService(),
            fee_service=SimulatedFeeService(),
        )

    @pytest.mark.asyncio
    async def test_validate_complete_draft(self, uc):
        base = _draft_dict(
            destination_country="MX",
            amount_units=500,
            amount_nanos=0,
            amount_currency="USD",
            beneficiary_name="Maria Garcia",
            beneficiary_account="1234567890",
            delivery_method=DeliveryMethod.BANK_DEPOSIT,
        )
        draft = await uc.execute(base)
        assert draft.status == TransferStatus.VALIDATED
        assert draft.fee_units is not None
        assert draft.receive_amount_units is not None
        assert draft.destination_currency == "MXN"

    @pytest.mark.asyncio
    async def test_validate_incomplete_draft_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute({})

    @pytest.mark.asyncio
    async def test_validate_unsupported_corridor_raises(self, uc):
        # GB only supports BANK_DEPOSIT — MOBILE_WALLET is unsupported there
        base = _draft_dict(
            destination_country="GB",
            amount_units=100,
            amount_nanos=0,
            amount_currency="USD",
            beneficiary_name="Test User",
            beneficiary_account="GB12345",
            delivery_method=DeliveryMethod.MOBILE_WALLET,
        )
        with pytest.raises(UnsupportedCorridorError):
            await uc.execute(base)


# ── ConfirmTransferUseCase ────────────────────────────────────────────────────

class _InMemoryUserAccountRepository(UserAccountRepository):
    """Minimal in-memory UserAccountRepository for ConfirmTransferUseCase tests."""

    def __init__(self, initial_balance: "Decimal | None" = None) -> None:
        from decimal import Decimal
        self._balance = initial_balance if initial_balance is not None else Decimal("1000")
        self._user_id = "test-user"

    async def create(self, account: UserAccount) -> UserAccount:
        return account

    async def get_by_username(self, username: str):
        return None

    async def get_by_id(self, user_id: str):
        if user_id != self._user_id:
            return None
        bal = Money.from_decimal(self._balance, "USD")
        return UserAccount(
            id=self._user_id,
            username="tester",
            password_hash="x",
            balance_units=bal.units,
            balance_nanos=bal.nanos,
        )

    async def add_funds(self, user_id: str, units: int, nanos: int) -> UserAccount:
        delta = Money(units=units, nanos=nanos, currency_code="").to_decimal()
        self._balance += delta
        return await self.get_by_id(user_id)

    async def deduct_funds(self, user_id: str, units: int, nanos: int) -> UserAccount:
        from decimal import Decimal
        delta = Money(units=units, nanos=nanos, currency_code="").to_decimal()
        if self._balance < delta:
            raise InsufficientFundsError(str(delta), str(self._balance))
        self._balance -= delta
        return await self.get_by_id(user_id)


class TestConfirmTransferUseCase:
    @pytest.fixture
    def uc(self, mock_transfer_repo):
        return ConfirmTransferUseCase(mock_transfer_repo)

    @pytest.mark.asyncio
    async def test_confirm_validated_transfer(self, uc):
        draft = await uc.execute(_validated_draft_dict(), "sess-123", "user-456")
        assert draft.status == TransferStatus.CONFIRMED
        assert draft.confirmation_code is not None
        assert draft.confirmation_code.startswith("SM-")
        assert draft.id is not None

    @pytest.mark.asyncio
    async def test_confirm_unvalidated_raises(self, uc):
        base = _draft_dict(status=TransferStatus.COLLECTING)
        with pytest.raises(InvalidFieldError):
            await uc.execute(base, "sess-1", "user-1")

    @pytest.mark.asyncio
    async def test_confirm_persists_to_repository(self, uc, mock_transfer_repo):
        draft = await uc.execute(_validated_draft_dict(), "sess-123", "user-456")
        stored = await mock_transfer_repo.get_by_id(draft.id)
        assert stored is not None
        assert stored.confirmation_code == draft.confirmation_code

    @pytest.mark.asyncio
    async def test_confirm_sets_session_and_user_id(self, uc):
        draft = await uc.execute(_validated_draft_dict(), "my-session", "my-user")
        assert draft.session_id == "my-session"
        assert draft.user_id == "my-user"

    @pytest.mark.asyncio
    async def test_confirm_with_sufficient_balance_succeeds(self, mock_transfer_repo):
        from decimal import Decimal
        user_repo = _InMemoryUserAccountRepository(initial_balance=Decimal("1000"))
        uc = ConfirmTransferUseCase(mock_transfer_repo, user_account_repository=user_repo)
        draft = await uc.execute(_validated_draft_dict(), "sess", "test-user")
        assert draft.status == TransferStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_confirm_without_account_still_succeeds(self, mock_transfer_repo):
        # user_id has no matching account → falls back to save() without deduction
        user_repo = _InMemoryUserAccountRepository(initial_balance=None)
        uc = ConfirmTransferUseCase(mock_transfer_repo, user_account_repository=user_repo)
        draft = await uc.execute(_validated_draft_dict(), "sess", "unknown-user")
        assert draft.status == TransferStatus.CONFIRMED


# ── GetCorridorsUseCase ───────────────────────────────────────────────────────

class TestGetCorridorsUseCase:
    @pytest.fixture
    def uc(self, in_memory_corridor_repo):
        return GetCorridorsUseCase(in_memory_corridor_repo)

    @pytest.mark.asyncio
    async def test_get_supported_countries(self, uc):
        countries = await uc.get_supported_countries()
        assert isinstance(countries, list)
        assert "MX" in countries

    @pytest.mark.asyncio
    async def test_get_delivery_methods_for_country(self, uc):
        methods = await uc.get_delivery_methods("MX")
        assert isinstance(methods, list)
        assert len(methods) > 0

    @pytest.mark.asyncio
    async def test_get_delivery_methods_unknown_country(self, uc):
        methods = await uc.get_delivery_methods("ZZ")
        assert methods == []
