"""Unit tests for ADK tool functions."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from send_money.domain.entities import TransferDraft, UserAccount
from send_money.domain.enums import DeliveryMethod, TransferStatus
from send_money.domain.errors import AuthenticationError, InsufficientFundsError, UsernameAlreadyExistsError
from send_money.domain.repositories import UserAccountRepository
from send_money.domain.value_objects import Money


# ── Helpers ───────────────────────────────────────────────────────────────────

class _InMemoryUserAccountRepository(UserAccountRepository):
    """Minimal in-memory UserAccountRepository for tool tests."""

    def __init__(self, balance: Decimal = Decimal("1000")) -> None:
        self._balance = balance
        self._user_id = "test-user"
        self._accounts: dict[str, UserAccount] = {}

    async def create(self, account: UserAccount) -> UserAccount:
        if account.username in {a.username for a in self._accounts.values()}:
            raise UsernameAlreadyExistsError(account.username)
        self._accounts[account.id] = account
        return account

    async def get_by_username(self, username: str):
        for account in self._accounts.values():
            if account.username == username:
                return account
        # Also support the default test-user that was pre-seeded before the accounts dict
        if username == "tester":
            bal = Money.from_decimal(self._balance, "USD")
            return UserAccount(
                id=self._user_id,
                username="tester",
                password_hash="x",
                balance_units=bal.units,
                balance_nanos=bal.nanos,
            )
        return None

    async def get_by_id(self, user_id: str):
        if user_id in self._accounts:
            return self._accounts[user_id]
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
        delta = Money(units=units, nanos=nanos, currency_code="").to_decimal()
        if self._balance < delta:
            raise InsufficientFundsError(str(delta), str(self._balance))
        self._balance -= delta
        return await self.get_by_id(user_id)


def _make_container(corridor_repo=None, transfer_repo=None, user_repo=None):
    """Build a minimal Container-like object with real use case instances."""
    from send_money.application.use_cases.add_funds import AddFundsUseCase
    from send_money.application.use_cases.collect_transfer_details import CollectTransferDetailsUseCase
    from send_money.application.use_cases.confirm_transfer import ConfirmTransferUseCase
    from send_money.adapters.persistence.beneficiary_repository import InMemoryBeneficiaryRepository
    from send_money.application.use_cases.create_account import CreateAccountUseCase
    from send_money.application.use_cases.get_balance import GetBalanceUseCase
    from send_money.application.use_cases.get_corridors import GetCorridorsUseCase
    from send_money.application.use_cases.list_beneficiaries import ListBeneficiariesUseCase
    from send_money.application.use_cases.login import LoginUseCase
    from send_money.application.use_cases.save_beneficiary import SaveBeneficiaryUseCase
    from send_money.application.use_cases.validate_transfer import ValidateTransferUseCase
    from send_money.infrastructure.simulated_services import (
        SimulatedExchangeRateService,
        SimulatedFeeService,
    )

    if user_repo is None:
        user_repo = _InMemoryUserAccountRepository()
    beneficiary_repo = InMemoryBeneficiaryRepository()

    container = MagicMock()
    container.collect_uc = CollectTransferDetailsUseCase(corridor_repo)
    container.validate_uc = ValidateTransferUseCase(
        corridor_repo,
        SimulatedExchangeRateService(),
        SimulatedFeeService(),
    )
    container.confirm_uc = ConfirmTransferUseCase(transfer_repo)
    container.corridors_uc = GetCorridorsUseCase(corridor_repo)
    container.add_funds_uc = AddFundsUseCase(user_repo)
    container.get_balance_uc = GetBalanceUseCase(user_repo)
    container.create_account_uc = CreateAccountUseCase(user_repo)
    container.login_uc = LoginUseCase(user_repo)
    container.list_beneficiaries_uc = ListBeneficiariesUseCase(beneficiary_repo)
    container.save_beneficiary_uc = SaveBeneficiaryUseCase(beneficiary_repo)
    return container


def _validated_state() -> dict:
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
    return {"transfer_draft": draft.to_state_dict()}


# ── update_transfer_field ─────────────────────────────────────────────────────

class TestUpdateTransferField:
    @pytest.fixture
    def tools(self, in_memory_corridor_repo, mock_transfer_repo):
        from send_money.adapters.agent.tools import create_tools
        container = _make_container(in_memory_corridor_repo, mock_transfer_repo)
        return {fn.__name__: fn for fn in create_tools(container)}

    @pytest.mark.asyncio
    async def test_update_valid_field(self, tools, mock_tool_context):
        result = await tools["update_transfer_field"]("destination_country", "MX", mock_tool_context)
        assert result["status"] == "updated"
        assert mock_tool_context.state["transfer_draft"]["destination_country"] == "MX"

    @pytest.mark.asyncio
    async def test_update_invalid_country_returns_error(self, tools, mock_tool_context):
        result = await tools["update_transfer_field"]("destination_country", "ZZ", mock_tool_context)
        assert result["status"] == "error"
        assert "ZZ" in result["message"]

    @pytest.mark.asyncio
    async def test_update_returns_missing_fields(self, tools, mock_tool_context):
        result = await tools["update_transfer_field"]("destination_country", "MX", mock_tool_context)
        assert "missing_fields" in result
        assert "amount_units" in result["missing_fields"]

    @pytest.mark.asyncio
    async def test_update_amount_stores_in_state(self, tools, mock_tool_context):
        await tools["update_transfer_field"]("amount", "150.00", mock_tool_context)
        draft = mock_tool_context.state["transfer_draft"]
        assert draft["amount_units"] == 150
        assert draft["amount_nanos"] == 0


# ── update_transfer_field — beneficiary_account ───────────────────────────────

class TestUpdateTransferFieldBeneficiaryAccount:
    @pytest.fixture
    def tools(self, in_memory_corridor_repo, mock_transfer_repo):
        from send_money.adapters.agent.tools import create_tools
        container = _make_container(in_memory_corridor_repo, mock_transfer_repo)
        return {fn.__name__: fn for fn in create_tools(container)}

    @pytest.mark.asyncio
    async def test_set_beneficiary_account(self, tools, mock_tool_context):
        result = await tools["update_transfer_field"]("beneficiary_account", "1234567890", mock_tool_context)
        assert result["status"] == "updated"
        assert mock_tool_context.state["transfer_draft"]["beneficiary_account"] == "1234567890"

    @pytest.mark.asyncio
    async def test_beneficiary_account_in_missing_fields_initially(self, tools, mock_tool_context):
        result = await tools["update_transfer_field"]("destination_country", "MX", mock_tool_context)
        assert "beneficiary_account" in result["missing_fields"]


# ── validate_transfer ─────────────────────────────────────────────────────────

class TestValidateTransfer:
    @pytest.fixture
    def tools(self, in_memory_corridor_repo, mock_transfer_repo):
        from send_money.adapters.agent.tools import create_tools
        container = _make_container(in_memory_corridor_repo, mock_transfer_repo)
        return {fn.__name__: fn for fn in create_tools(container)}

    @pytest.mark.asyncio
    async def test_validate_complete_draft(self, tools, mock_tool_context):
        # Prime state with all required fields
        mock_tool_context.state["transfer_draft"] = TransferDraft(
            destination_country="MX",
            amount_units=500,
            amount_nanos=0,
            amount_currency="USD",
            beneficiary_name="Maria Garcia",
            beneficiary_account="1234567890",
            delivery_method=DeliveryMethod.BANK_DEPOSIT,
        ).to_state_dict()
        result = await tools["validate_transfer"](mock_tool_context)
        assert result["status"] == "validated"
        assert "fee" in result
        assert "receive_amount" in result

    @pytest.mark.asyncio
    async def test_validate_incomplete_returns_error(self, tools, mock_tool_context):
        result = await tools["validate_transfer"](mock_tool_context)
        assert result["status"] == "error"


# ── confirm_transfer ──────────────────────────────────────────────────────────

class TestConfirmTransfer:
    @pytest.fixture
    def tools(self, in_memory_corridor_repo, mock_transfer_repo):
        from send_money.adapters.agent.tools import create_tools
        container = _make_container(in_memory_corridor_repo, mock_transfer_repo)
        return {fn.__name__: fn for fn in create_tools(container)}

    @pytest.mark.asyncio
    async def test_confirm_validated_transfer(self, tools, mock_tool_context):
        mock_tool_context.state.update(_validated_state())
        result = await tools["confirm_transfer"](mock_tool_context)
        assert result["status"] == "confirmed"
        assert result["confirmation_code"].startswith("SM-")

    @pytest.mark.asyncio
    async def test_confirm_unvalidated_returns_error(self, tools, mock_tool_context):
        result = await tools["confirm_transfer"](mock_tool_context)
        assert result["status"] == "error"


# ── get_supported_countries ───────────────────────────────────────────────────

class TestGetSupportedCountries:
    @pytest.fixture
    def tools(self, in_memory_corridor_repo, mock_transfer_repo):
        from send_money.adapters.agent.tools import create_tools
        container = _make_container(in_memory_corridor_repo, mock_transfer_repo)
        return {fn.__name__: fn for fn in create_tools(container)}

    @pytest.mark.asyncio
    async def test_returns_country_list(self, tools, mock_tool_context):
        result = await tools["get_supported_countries"](mock_tool_context)
        assert "supported_countries" in result
        assert any("MX" in c for c in result["supported_countries"])


# ── get_delivery_methods ──────────────────────────────────────────────────────

class TestGetDeliveryMethods:
    @pytest.fixture
    def tools(self, in_memory_corridor_repo, mock_transfer_repo):
        from send_money.adapters.agent.tools import create_tools
        container = _make_container(in_memory_corridor_repo, mock_transfer_repo)
        return {fn.__name__: fn for fn in create_tools(container)}

    @pytest.mark.asyncio
    async def test_returns_methods_for_country(self, tools, mock_tool_context):
        result = await tools["get_delivery_methods"]("MX", mock_tool_context)
        assert "Mexico" in result["country"]
        assert len(result["delivery_methods"]) > 0
        # Methods are now human-readable labels, not raw enum values
        assert all("_" not in m for m in result["delivery_methods"])

    @pytest.mark.asyncio
    async def test_unknown_country_returns_empty(self, tools, mock_tool_context):
        result = await tools["get_delivery_methods"]("ZZ", mock_tool_context)
        assert result["delivery_methods"] == []


# ── add_funds ─────────────────────────────────────────────────────────────────

class TestAddFunds:
    @pytest.fixture
    def tools(self, in_memory_corridor_repo, mock_transfer_repo):
        from send_money.adapters.agent.tools import create_tools
        container = _make_container(in_memory_corridor_repo, mock_transfer_repo)
        return {fn.__name__: fn for fn in create_tools(container)}

    @pytest.mark.asyncio
    async def test_add_funds_returns_new_balance(self, tools, mock_tool_context):
        result = await tools["add_funds"]("500", "USD", mock_tool_context)
        assert result["status"] == "funds_added"
        assert "new_balance" in result
        assert "USD" in result["new_balance"]

    @pytest.mark.asyncio
    async def test_add_funds_zero_returns_error(self, tools, mock_tool_context):
        result = await tools["add_funds"]("0", "USD", mock_tool_context)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_add_funds_negative_returns_error(self, tools, mock_tool_context):
        result = await tools["add_funds"]("-100", "USD", mock_tool_context)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_add_funds_no_user_returns_error(self, tools, mock_tool_context):
        mock_tool_context.invocation_context.session.user_id = ""
        result = await tools["add_funds"]("100", "USD", mock_tool_context)
        assert result["status"] == "error"


# ── get_balance ───────────────────────────────────────────────────────────────

class TestGetBalance:
    @pytest.fixture
    def tools(self, in_memory_corridor_repo, mock_transfer_repo):
        from send_money.adapters.agent.tools import create_tools
        container = _make_container(in_memory_corridor_repo, mock_transfer_repo)
        return {fn.__name__: fn for fn in create_tools(container)}

    @pytest.mark.asyncio
    async def test_get_balance_returns_balance(self, tools, mock_tool_context):
        result = await tools["get_balance"](mock_tool_context)
        assert result["status"] == "ok"
        assert "balance" in result
        assert "currency" in result

    @pytest.mark.asyncio
    async def test_get_balance_no_user_returns_error(self, tools, mock_tool_context):
        mock_tool_context.invocation_context.session.user_id = ""
        result = await tools["get_balance"](mock_tool_context)
        assert result["status"] == "error"


# ── get_saved_beneficiaries ───────────────────────────────────────────────────

class TestGetSavedBeneficiaries:
    @pytest.fixture
    def setup(self, in_memory_corridor_repo, mock_transfer_repo):
        """Returns (tools_dict, save_uc) sharing the same beneficiary_repo."""
        from send_money.adapters.persistence.beneficiary_repository import InMemoryBeneficiaryRepository
        from send_money.adapters.agent.tools import create_tools
        from send_money.application.use_cases.list_beneficiaries import ListBeneficiariesUseCase
        from send_money.application.use_cases.save_beneficiary import SaveBeneficiaryUseCase

        shared_repo = InMemoryBeneficiaryRepository()
        container = _make_container(in_memory_corridor_repo, mock_transfer_repo)
        container.list_beneficiaries_uc = ListBeneficiariesUseCase(shared_repo)
        container.save_beneficiary_uc = SaveBeneficiaryUseCase(shared_repo)
        tools = {fn.__name__: fn for fn in create_tools(container)}
        save_uc = SaveBeneficiaryUseCase(shared_repo)
        return tools, save_uc

    @pytest.mark.asyncio
    async def test_returns_empty_list_initially(self, setup, mock_tool_context):
        tools, _ = setup
        result = await tools["get_saved_beneficiaries"](mock_tool_context)
        assert result["status"] == "ok"
        assert result["beneficiaries"] == []

    @pytest.mark.asyncio
    async def test_no_user_returns_error(self, setup, mock_tool_context):
        tools, _ = setup
        mock_tool_context.state.pop("user_id", None)
        mock_tool_context.invocation_context.session.user_id = ""
        result = await tools["get_saved_beneficiaries"](mock_tool_context)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_returns_saved_beneficiaries(self, setup, mock_tool_context):
        tools, save_uc = setup
        await save_uc.execute("test-user", "Maria Garcia", "1234567890", "MX")
        await save_uc.execute("test-user", "Carlos Lopez", "0987654321", "CO")
        result = await tools["get_saved_beneficiaries"](mock_tool_context)
        assert result["status"] == "ok"
        assert len(result["beneficiaries"]) == 2
        names = [b["name"] for b in result["beneficiaries"]]
        assert "Maria Garcia" in names
        assert "Carlos Lopez" in names


# ── create_account ────────────────────────────────────────────────────────────

class TestCreateAccount:
    @pytest.fixture
    def tools(self, in_memory_corridor_repo, mock_transfer_repo):
        from send_money.adapters.agent.tools import create_tools
        container = _make_container(in_memory_corridor_repo, mock_transfer_repo)
        return {fn.__name__: fn for fn in create_tools(container)}

    @pytest.mark.asyncio
    async def test_create_account_success(self, tools, mock_tool_context):
        mock_tool_context.state.pop("user_id", None)
        result = await tools["create_account"]("alice", "secret123", mock_tool_context)
        assert result["status"] == "account_created"
        assert result["username"] == "alice"
        assert mock_tool_context.state["user_id"]
        assert mock_tool_context.state["username"] == "alice"

    @pytest.mark.asyncio
    async def test_create_duplicate_username_returns_error(self, tools, mock_tool_context):
        mock_tool_context.state.pop("user_id", None)
        await tools["create_account"]("alice", "secret123", mock_tool_context)
        result = await tools["create_account"]("alice", "otherpass", mock_tool_context)
        assert result["status"] == "error"
        assert "alice" in result["message"]

    @pytest.mark.asyncio
    async def test_create_account_sets_user_id_in_state(self, tools, mock_tool_context):
        mock_tool_context.state.pop("user_id", None)
        result = await tools["create_account"]("bob", "pass1234", mock_tool_context)
        assert result["status"] == "account_created"
        assert mock_tool_context.state.get("user_id") is not None


# ── login ──────────────────────────────────────────────────────────────────────

class TestLogin:
    @pytest.fixture
    def tools(self, in_memory_corridor_repo, mock_transfer_repo):
        from send_money.adapters.agent.tools import create_tools
        container = _make_container(in_memory_corridor_repo, mock_transfer_repo)
        return {fn.__name__: fn for fn in create_tools(container)}

    @pytest.mark.asyncio
    async def test_login_success(self, tools, mock_tool_context):
        # First create an account so login can find it
        mock_tool_context.state.pop("user_id", None)
        await tools["create_account"]("charlie", "mypassword", mock_tool_context)
        mock_tool_context.state.pop("user_id", None)

        result = await tools["login"]("charlie", "mypassword", mock_tool_context)
        assert result["status"] == "logged_in"
        assert result["username"] == "charlie"
        assert mock_tool_context.state["user_id"]
        assert mock_tool_context.state["username"] == "charlie"

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_error(self, tools, mock_tool_context):
        mock_tool_context.state.pop("user_id", None)
        await tools["create_account"]("dave", "correctpass", mock_tool_context)
        mock_tool_context.state.pop("user_id", None)

        result = await tools["login"]("dave", "wrongpass", mock_tool_context)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_login_unknown_user_returns_error(self, tools, mock_tool_context):
        result = await tools["login"]("nobody", "pass", mock_tool_context)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_login_sets_user_id_in_state(self, tools, mock_tool_context):
        mock_tool_context.state.pop("user_id", None)
        await tools["create_account"]("eve", "pass5678", mock_tool_context)
        mock_tool_context.state.pop("user_id", None)

        await tools["login"]("eve", "pass5678", mock_tool_context)
        assert mock_tool_context.state.get("user_id") is not None


# ── Decimal precision regression ──────────────────────────────────────────────

class TestDecimalPrecision:
    """Regression tests for the decimal rounding bug fix (was NUMERIC(19,4))."""

    def test_0_99999_not_rounded_to_1(self):
        """Core regression: 0.99999 must not be stored as 1.0."""
        from send_money.adapters.persistence.transfer_repository import _money_to_decimal
        result = _money_to_decimal(0, 999990000)
        assert result == Decimal("0.999990000")
        assert result != Decimal("1"), "Bug regressed: 0.99999 was rounded to 1.0"

    def test_full_nano_precision_preserved(self):
        from send_money.adapters.persistence.transfer_repository import _money_to_decimal
        result = _money_to_decimal(42, 123456789)
        assert result == Decimal("42.123456789")

    def test_whole_amount_preserved(self):
        from send_money.adapters.persistence.transfer_repository import _money_to_decimal
        result = _money_to_decimal(500, 0)
        assert result == Decimal("500.000000000")

    def test_none_units_returns_zero(self):
        from send_money.adapters.persistence.transfer_repository import _money_to_decimal
        result = _money_to_decimal(None, None)
        assert result == Decimal("0")
