"""LangfuseAuditPlugin — banking-domain metadata and scores on every trace.

The OTLP bridge (otel_setup.py) already captures all LLM calls, tool calls,
and token usage automatically.  This plugin supplements that with:

  • Transfer metadata snapshot after each tool call (country, amount, status)
  • field_completeness score at the end of each invocation
  • Session → user mapping for compliance audit trails
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from google.adk.plugins.base_plugin import BasePlugin

if TYPE_CHECKING:
    from google.adk.agents.base_agent import BaseAgent
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.tool_context import ToolContext


_AUDIT_TOOLS = {"update_transfer_field", "validate_transfer", "confirm_transfer"}
_REQUIRED_FIELDS = ["destination_country", "amount_currency", "beneficiary_name", "delivery_method"]


class LangfuseAuditPlugin(BasePlugin):
    """Attaches transfer-domain metadata and quality scores to Langfuse traces."""

    def __init__(self, langfuse_client: Any) -> None:
        super().__init__(name="langfuse_audit")
        self._langfuse = langfuse_client
        # invocation_id → langfuse Trace object
        self._traces: dict[str, Any] = {}

    async def before_run_callback(self, *, invocation_context: "InvocationContext") -> None:
        span = self._langfuse.start_observation(
            name="send-money-transfer",
            as_type="span",
            metadata={
                "app_name": invocation_context.app_name,
                "invocation_id": invocation_context.invocation_id,
                "user_id": invocation_context.user_id,
                "session_id": invocation_context.session.id,
            },
        )
        self._traces[invocation_context.invocation_id] = span

        # Write Langfuse IDs into session state upfront so tools (e.g.
        # confirm_transfer) can read them before after_tool_callback fires.
        invocation_context.session.state["_langfuse_trace_id"] = getattr(span, "trace_id", "")
        invocation_context.session.state["_langfuse_observation_id"] = getattr(span, "id", "")

    async def after_tool_callback(
        self,
        *,
        tool: "BaseTool",
        tool_args: dict[str, Any],
        tool_context: "ToolContext",
        result: dict,
    ) -> None:
        if tool.name not in _AUDIT_TOOLS:
            return
        trace = self._traces.get(tool_context.invocation_id)
        if trace is None:
            return
        draft: dict = tool_context.state.get("transfer_draft", {})
        trace.update(
            metadata={
                "transfer_country": draft.get("destination_country"),
                "transfer_amount_currency": draft.get("amount_currency"),
                "transfer_status": draft.get("status"),
                "last_tool": tool.name,
            },
        )

    async def after_run_callback(self, *, invocation_context: "InvocationContext") -> None:
        trace = self._traces.pop(invocation_context.invocation_id, None)
        if trace is None:
            return
        draft: dict = invocation_context.session.state.get("transfer_draft", {})
        filled = sum(1 for f in _REQUIRED_FIELDS if draft.get(f))
        completeness = filled / len(_REQUIRED_FIELDS)
        trace.score(name="field_completeness", value=completeness)
        trace.end()

    async def close(self) -> None:
        self._langfuse.flush()
