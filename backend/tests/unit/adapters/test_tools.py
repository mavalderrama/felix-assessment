"""Unit tests for ADK tool functions."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from send_money.domain.entities import TransferDraft
from send_money.domain.enums import DeliveryMethod, TransferStatus


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_container(corridor_repo=None, transfer_repo=None):
    """Build a minimal Container-like object with mocked use cases."""
    from send_money.application.use_cases.collect_transfer_details import CollectTransferDetailsUseCase
    from send_money.application.use_cases.confirm_transfer import ConfirmTransferUseCase
    from send_money.application.use_cases.get_corridors import GetCorridorsUseCase
    from send_money.application.use_cases.validate_transfer import ValidateTransferUseCase
    from send_money.infrastructure.simulated_services import (
        SimulatedExchangeRateService,
        SimulatedFeeService,
    )

    container = MagicMock()
    container.collect_uc = CollectTransferDetailsUseCase(corridor_repo)
    container.validate_uc = ValidateTransferUseCase(
        corridor_repo,
        SimulatedExchangeRateService(),
        SimulatedFeeService(),
    )
    container.confirm_uc = ConfirmTransferUseCase(transfer_repo)
    container.corridors_uc = GetCorridorsUseCase(corridor_repo)
    return container


def _validated_state() -> dict:
    draft = TransferDraft(
        destination_country="MX",
        amount_units=500,
        amount_nanos=0,
        amount_currency="USD",
        beneficiary_name="Maria Garcia",
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
        assert "MX" in result["supported_countries"]


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
        assert result["country"] == "MX"
        assert len(result["delivery_methods"]) > 0

    @pytest.mark.asyncio
    async def test_unknown_country_returns_empty(self, tools, mock_tool_context):
        result = await tools["get_delivery_methods"]("ZZ", mock_tool_context)
        assert result["delivery_methods"] == []
