"""Unit tests for beneficiary use cases."""
from __future__ import annotations

import pytest

from send_money.adapters.persistence.beneficiary_repository import InMemoryBeneficiaryRepository
from send_money.application.use_cases.list_beneficiaries import ListBeneficiariesUseCase
from send_money.application.use_cases.save_beneficiary import SaveBeneficiaryUseCase
from send_money.domain.errors import InvalidFieldError


# ── TestSaveBeneficiaryUseCase ─────────────────────────────────────────────────

class TestSaveBeneficiaryUseCase:
    @pytest.fixture
    def uc(self):
        return SaveBeneficiaryUseCase(InMemoryBeneficiaryRepository())

    @pytest.mark.asyncio
    async def test_saves_new_beneficiary(self, uc):
        b = await uc.execute("user-1", "Maria Garcia", "1234567890", "MX", "BANK_DEPOSIT")
        assert b.id is not None
        assert b.name == "Maria Garcia"
        assert b.account_number == "1234567890"
        assert b.country_code == "MX"

    @pytest.mark.asyncio
    async def test_returns_existing_on_duplicate_name(self, uc):
        b1 = await uc.execute("user-1", "Maria Garcia", "1234567890")
        b2 = await uc.execute("user-1", "Maria Garcia", "9999999999")
        assert b1.id == b2.id
        assert b2.account_number == "9999999999"

    @pytest.mark.asyncio
    async def test_case_insensitive_name_match(self, uc):
        b1 = await uc.execute("user-1", "Maria Garcia", "1234567890")
        b2 = await uc.execute("user-1", "maria garcia", "9999999999")
        assert b1.id == b2.id

    @pytest.mark.asyncio
    async def test_different_users_same_name_creates_separate_records(self, uc):
        b1 = await uc.execute("user-1", "Maria Garcia", "111")
        b2 = await uc.execute("user-2", "Maria Garcia", "222")
        assert b1.id != b2.id

    @pytest.mark.asyncio
    async def test_short_name_raises(self, uc):
        with pytest.raises(InvalidFieldError) as exc_info:
            await uc.execute("user-1", "M", "1234567890")
        assert "beneficiary_name" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_account_raises(self, uc):
        with pytest.raises(InvalidFieldError) as exc_info:
            await uc.execute("user-1", "Maria Garcia", "")
        assert "beneficiary_account" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_whitespace_account_raises(self, uc):
        with pytest.raises(InvalidFieldError):
            await uc.execute("user-1", "Maria Garcia", "   ")

    @pytest.mark.asyncio
    async def test_updates_country_on_re_save(self, uc):
        await uc.execute("user-1", "Maria Garcia", "123", "MX")
        b = await uc.execute("user-1", "Maria Garcia", "123", "CO")
        assert b.country_code == "CO"


# ── TestListBeneficiariesUseCase ───────────────────────────────────────────────

class TestListBeneficiariesUseCase:
    @pytest.fixture
    def repo(self):
        return InMemoryBeneficiaryRepository()

    @pytest.fixture
    def uc(self, repo):
        return ListBeneficiariesUseCase(repo)

    @pytest.fixture
    def save_uc(self, repo):
        return SaveBeneficiaryUseCase(repo)

    @pytest.mark.asyncio
    async def test_returns_empty_for_new_user(self, uc):
        result = await uc.execute("user-unknown")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_saved_beneficiaries(self, uc, save_uc):
        await save_uc.execute("user-1", "Alice Smith", "111")
        await save_uc.execute("user-1", "Bob Jones", "222")
        result = await uc.execute("user-1")
        assert len(result) == 2
        names = [b.name for b in result]
        assert "Alice Smith" in names
        assert "Bob Jones" in names

    @pytest.mark.asyncio
    async def test_returns_only_current_user_beneficiaries(self, uc, save_uc):
        await save_uc.execute("user-1", "Alice Smith", "111")
        await save_uc.execute("user-2", "Bob Jones", "222")
        result = await uc.execute("user-1")
        assert len(result) == 1
        assert result[0].name == "Alice Smith"

    @pytest.mark.asyncio
    async def test_results_ordered_by_name(self, uc, save_uc):
        await save_uc.execute("user-1", "Zara White", "333")
        await save_uc.execute("user-1", "Alice Smith", "111")
        await save_uc.execute("user-1", "Maria Garcia", "222")
        result = await uc.execute("user-1")
        names = [b.name for b in result]
        assert names == sorted(names, key=str.lower)
