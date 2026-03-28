"""ADK agent factory."""
from __future__ import annotations

from typing import TYPE_CHECKING

from google.adk import Agent

from send_money.adapters.agent.instructions import SEND_MONEY_INSTRUCTION
from send_money.adapters.agent.tools import create_tools

if TYPE_CHECKING:
    from send_money.infrastructure.container import Container


def create_send_money_agent(container: "Container") -> Agent:
    """Construct and return the configured Send Money LlmAgent."""
    return Agent(
        name="send_money_agent",
        model="gemini-2.5-flash",
        instruction=SEND_MONEY_INSTRUCTION,
        tools=create_tools(container),
        # Store the agent's final text response in session state for easy access
        output_key="agent_response",
        # Single agent — no peer or parent to transfer to
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
