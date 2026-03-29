"""ADK agent factory."""
from __future__ import annotations

from typing import TYPE_CHECKING, Union

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

from send_money.adapters.agent.guardrails import check_tool_args, check_user_input
from send_money.adapters.agent.instructions import build_instruction
from send_money.adapters.agent.tools import create_tools

if TYPE_CHECKING:
    from send_money.infrastructure.container import Container

# Default models per provider (used when LLM_MODEL is not explicitly set)
_PROVIDER_DEFAULTS = {
    "openai": "openai/gpt-4o",
    "anthropic": "anthropic/claude-sonnet-4-20250514",
    "google": "gemini-2.5-flash",
}


def _resolve_model(settings) -> Union[str, LiteLlm]:
    """Return either a Gemini model name string or a LiteLlm wrapper.

    Resolution order:
    1. LLM_MODEL env var (explicit override — use as-is)
    2. Auto-detect from whichever API key is set:
       OPENAI_API_KEY → openai/gpt-4o
       ANTHROPIC_API_KEY → anthropic/claude-sonnet-4-20250514
       GOOGLE_API_KEY → gemini-2.5-flash
    3. Fall back to gemini-2.5-flash (will fail at runtime if no key is set)
    """
    model_str: str = settings.LLM_MODEL

    if not model_str:
        if settings.OPENAI_API_KEY:
            model_str = _PROVIDER_DEFAULTS["openai"]
        elif settings.ANTHROPIC_API_KEY:
            model_str = _PROVIDER_DEFAULTS["anthropic"]
        else:
            model_str = _PROVIDER_DEFAULTS["google"]

    if model_str.startswith("gemini"):
        return model_str  # ADK handles Gemini natively

    return LiteLlm(model=model_str)


def create_send_money_agent(container: "Container") -> Agent:
    """Construct and return the configured Send Money LlmAgent."""
    from django.conf import settings

    model = _resolve_model(settings)

    return Agent(
        name="send_money_agent",
        model=model,
        instruction=build_instruction,
        tools=create_tools(container),
        # Store the agent's final text response in session state for easy access
        output_key="agent_response",
        # Single agent — no peer or parent to transfer to
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        # Guardrails: inspect user input before the LLM call; validate tool
        # arguments before each tool executes.
        before_model_callback=check_user_input,
        before_tool_callback=check_tool_args,
    )
