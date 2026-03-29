"""Unit tests for beneficiary use cases."""

from __future__ import annotations

import pytest

from send_money.adapters.persistence.beneficiary_repository import (
    InMemoryBeneficiaryRepository,
)
from send_money.application.use_cases.list_beneficiaries import ListBeneficiariesUseCase
from send_money.application.use_cases.save_beneficiary import SaveBeneficiaryUseCase
from send_money.domain.errors import InvalidFieldError

# ── TestSaveBeneficiaryUseCase ─────────────────────────────────────────────────


class TestSaveBeneficiaryUseCase:
    @pytest.fixture
    def uc(self) -> SaveBeneficiaryUseCase:
        return SaveBeneficiaryUseCase(InMemoryBeneficiaryRepository())

    @pytest.mark.asyncio
    async def test_saves_new_beneficiary(self, uc: SaveBeneficiaryUseCase) -> None:
        b = await uc.execute(
            "user-1", "Maria Garcia", "1234567890", "MX", "BANK_DEPOSIT"
        )
        assert b.id is not None
        assert b.name == "Maria Garcia"
        assert b.account_number == "1234567890"
        assert b.country_code == "MX"

    @pytest.mark.asyncio
    async def test_same_name_different_account_creates_new_entry(
        self, uc: SaveBeneficiaryUseCase
    ) -> None:
        b1 = await uc.execute("user-1", "Maria Garcia", "1234567890")
        b2 = await uc.execute("user-1", "Maria Garcia", "9999999999")
        assert b1.id != b2.id
        assert b1.account_number == "1234567890"
        assert b2.account_number == "9999999999"

    @pytest.mark.asyncio
    async def test_same_name_same_account_updates_existing(
        self, uc: SaveBeneficiaryUseCase
    ) -> None:
        b1 = await uc.execute("user-1", "Maria Garcia", "1234567890", "MX")
        b2 = await uc.execute("user-1", "Maria Garcia", "1234567890", "CO")
        assert b1.id == b2.id
        assert b2.country_code == "CO"

    @pytest.mark.asyncio
    async def test_case_insensitive_name_match_same_account_updates(
        self, uc: SaveBeneficiaryUseCase
    ) -> None:
        b1 = await uc.execute("user-1", "Maria Garcia", "1234567890", "MX")
        b2 = await uc.execute("user-1", "maria garcia", "1234567890", "CO")
        assert b1.id == b2.id
        assert b2.country_code == "CO"

    @pytest.mark.asyncio
    async def test_different_users_same_name_creates_separate_records(
        self, uc: SaveBeneficiaryUseCase
    ) -> None:
        b1 = await uc.execute("user-1", "Maria Garcia", "111")
        b2 = await uc.execute("user-2", "Maria Garcia", "222")
        assert b1.id != b2.id

    @pytest.mark.asyncio
    async def test_short_name_raises(self, uc: SaveBeneficiaryUseCase) -> None:
        with pytest.raises(InvalidFieldError) as exc_info:
            await uc.execute("user-1", "M", "1234567890")
        assert "beneficiary_name" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_account_raises(self, uc: SaveBeneficiaryUseCase) -> None:
        with pytest.raises(InvalidFieldError) as exc_info:
            await uc.execute("user-1", "Maria Garcia", "")
        assert "beneficiary_account" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_whitespace_account_raises(self, uc: SaveBeneficiaryUseCase) -> None:
        with pytest.raises(InvalidFieldError):
            await uc.execute("user-1", "Maria Garcia", "   ")

    @pytest.mark.asyncio
    async def test_updates_country_on_re_save_same_account(
        self, uc: SaveBeneficiaryUseCase
    ) -> None:
        await uc.execute("user-1", "Maria Garcia", "123", "MX")
        b = await uc.execute("user-1", "Maria Garcia", "123", "CO")
        assert b.country_code == "CO"

    @pytest.mark.asyncio
    async def test_different_accounts_create_separate_records(
        self, uc: SaveBeneficiaryUseCase
    ) -> None:
        b1 = await uc.execute("user-1", "Neyla Rios", "OLD_ACC", "CO", "BANK_DEPOSIT")
        b2 = await uc.execute("user-1", "Neyla Rios", "NEW_ACC", "CO", "BANK_DEPOSIT")
        assert b1.id != b2.id

    @pytest.mark.asyncio
    async def test_different_delivery_methods_same_account_create_separate_records(
        self, uc: SaveBeneficiaryUseCase
    ) -> None:
        b1 = await uc.execute("user-1", "Neyla Rios", "COL123", "CO", "BANK_DEPOSIT")
        b2 = await uc.execute("user-1", "Neyla Rios", "COL123", "CO", "CASH_PICKUP")
        assert b1.id != b2.id
        assert b1.delivery_method is not None
        assert b2.delivery_method is not None
        assert b1.delivery_method.value == "BANK_DEPOSIT"
        assert b2.delivery_method.value == "CASH_PICKUP"

    @pytest.mark.asyncio
    async def test_exact_match_name_account_delivery_updates(
        self, uc: SaveBeneficiaryUseCase
    ) -> None:
        b1 = await uc.execute("user-1", "Neyla Rios", "COL123", "MX", "BANK_DEPOSIT")
        b2 = await uc.execute("user-1", "Neyla Rios", "COL123", "CO", "BANK_DEPOSIT")
        assert b1.id == b2.id
        assert b2.country_code == "CO"

    @pytest.mark.asyncio
    async def test_multiple_entries_all_listed(
        self, uc: SaveBeneficiaryUseCase
    ) -> None:
        repo = InMemoryBeneficiaryRepository()
        uc2 = SaveBeneficiaryUseCase(repo)
        list_uc = ListBeneficiariesUseCase(repo)
        await uc2.execute("user-1", "Neyla Rios", "COL123", "CO", "BANK_DEPOSIT")
        await uc2.execute("user-1", "Neyla Rios", "COL123", "CO", "CASH_PICKUP")
        await uc2.execute("user-1", "Neyla Rios", "COL456", "CO", "BANK_DEPOSIT")
        result = await list_uc.execute("user-1")
        assert len(result) == 3


# ── TestListBeneficiariesUseCase ───────────────────────────────────────────────


class TestListBeneficiariesUseCase:
    @pytest.fixture
    def repo(self) -> InMemoryBeneficiaryRepository:
        return InMemoryBeneficiaryRepository()

    @pytest.fixture
    def uc(self, repo: InMemoryBeneficiaryRepository) -> ListBeneficiariesUseCase:
        return ListBeneficiariesUseCase(repo)

    @pytest.fixture
    def save_uc(self, repo: InMemoryBeneficiaryRepository) -> SaveBeneficiaryUseCase:
        return SaveBeneficiaryUseCase(repo)

    @pytest.mark.asyncio
    async def test_returns_empty_for_new_user(
        self, uc: ListBeneficiariesUseCase
    ) -> None:
        result = await uc.execute("user-unknown")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_saved_beneficiaries(
        self, uc: ListBeneficiariesUseCase, save_uc: SaveBeneficiaryUseCase
    ) -> None:
        await save_uc.execute("user-1", "Alice Smith", "111")
        await save_uc.execute("user-1", "Bob Jones", "222")
        result = await uc.execute("user-1")
        assert len(result) == 2
        names = [b.name for b in result]
        assert "Alice Smith" in names
        assert "Bob Jones" in names

    @pytest.mark.asyncio
    async def test_returns_only_current_user_beneficiaries(
        self, uc: ListBeneficiariesUseCase, save_uc: SaveBeneficiaryUseCase
    ) -> None:
        await save_uc.execute("user-1", "Alice Smith", "111")
        await save_uc.execute("user-2", "Bob Jones", "222")
        result = await uc.execute("user-1")
        assert len(result) == 1
        assert result[0].name == "Alice Smith"

    @pytest.mark.asyncio
    async def test_results_ordered_by_name(
        self, uc: ListBeneficiariesUseCase, save_uc: SaveBeneficiaryUseCase
    ) -> None:
        await save_uc.execute("user-1", "Zara White", "333")
        await save_uc.execute("user-1", "Alice Smith", "111")
        await save_uc.execute("user-1", "Maria Garcia", "222")
        result = await uc.execute("user-1")
        names = [b.name for b in result]
        assert names == sorted(names, key=str.lower)
