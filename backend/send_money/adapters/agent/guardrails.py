"""Input guardrails for the Send Money Agent.

Two ADK callback functions are exported:

- ``check_user_input`` — ``before_model_callback``
  Inspects the last user message before the LLM is called.  Returns a
  blocking ``LlmResponse`` if injection or abuse patterns are detected,
  preventing the LLM call entirely.

- ``check_tool_args`` — ``before_tool_callback``
  Validates tool arguments before a tool executes.  Returns an error dict
  to skip the real tool call when values are out-of-bounds or malicious.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

# ── Constants ─────────────────────────────────────────────────────────────────

#: Maximum characters allowed in a single user message.
_MAX_INPUT_LENGTH = 2_000

#: Maximum single add_funds transaction amount (domain business rule).
_MAX_ADD_FUNDS_AMOUNT = Decimal("100_000")

#: Maximum characters for any individual tool field value.
_MAX_FIELD_VALUE_LENGTH = 200

# Compiled patterns for prompt-injection detection.
# Each tuple is (pattern, description) — description is only used in tests.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?((previous|prior|your|the)\s+)?instructions?",
        r"disregard\s+(all\s+)?((previous|prior|your|the)\s+)?instructions?",
        r"forget\s+(all\s+|your\s+|previous\s+|prior\s+|the\s+)*instructions?",
        r"you\s+are\s+now\s+",
        r"pretend\s+(you\s+are|to\s+be)\s+",
        r"act\s+as\s+(a\s+|an\s+)?(?!the\s+recipient|the\s+beneficiary|my)",
        r"new\s+(system\s+)?instructions?\s*:",
        r"your\s+new\s+(role|persona|instructions?)\s+",
        r"system\s*:\s*",
        r"\bjailbreak\b",
        r"\bDAN\b",  # "Do Anything Now"
        r"override\s+(your\s+)?(previous\s+)?instructions?",
        r"reveal\s+(your\s+)?(system\s+)?prompt",
        r"print\s+(your\s+)?(system\s+)?prompt",
        r"show\s+(me\s+)?(your\s+)?(system\s+)?instructions?",
        r"what\s+are\s+your\s+(system\s+)?instructions?",
        r"repeat\s+(your\s+)?(system\s+)?instructions?",
    ]
]

# Code/template injection markers rejected inside tool field values.
_CODE_INJECTION_MARKERS = [
    "<script",
    "__import__",
    "eval(",
    "exec(",
    "{{",
    "{%",
    "os.system",
    "subprocess",
    "open(",
]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_last_user_text(llm_request: Any) -> str:
    """Return the text of the last user-role content in the request, or ''."""
    for content in reversed(llm_request.contents):
        if getattr(content, "role", None) == "user":
            parts = getattr(content, "parts", []) or []
            texts: list[str] = [
                str(getattr(p, "text", "")) for p in parts if getattr(p, "text", None)
            ]
            return " ".join(texts)
    return ""


def _blocking_response(message: str) -> Any:
    """Build a canned LlmResponse that replaces the real model call."""
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=message)],
        )
    )


# ── Public callbacks ──────────────────────────────────────────────────────────


def check_user_input(callback_context: Any, llm_request: Any) -> Any:
    """before_model_callback — block injection/abuse before the LLM is called.

    Returns an LlmResponse to short-circuit the model call, or None to proceed.
    """
    text = _extract_last_user_text(llm_request)

    # 1. Length check
    if len(text) > _MAX_INPUT_LENGTH:
        return _blocking_response(
            "Your message is too long. Please keep requests concise — "
            "I'm here to help with money transfers."
        )

    # 2. Injection pattern check
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return _blocking_response(
                "I can only help with money transfers and account management. "
                "How can I assist you with a transfer today?"
            )

    return None


def check_tool_args(
    tool: Any, args: dict[str, Any], tool_context: Any
) -> dict[str, Any] | None:
    """before_tool_callback — validate tool arguments before execution.

    Returns an error dict to skip the tool call, or None to proceed.
    """
    name = getattr(tool, "name", "")

    if name == "update_transfer_field":
        field_value: str = args.get("field_value", "") or ""

        # Length guard
        if len(field_value) > _MAX_FIELD_VALUE_LENGTH:
            return {
                "status": "error",
                "message": (
                    f"Field value is too long "
                    f"(max {_MAX_FIELD_VALUE_LENGTH} characters). "
                    "Please provide a shorter value."
                ),
            }

        # Code/template injection guard
        lower_value = field_value.lower()
        for marker in _CODE_INJECTION_MARKERS:
            if marker.lower() in lower_value:
                return {
                    "status": "error",
                    "message": "Invalid characters detected in the field value.",
                }

    elif name in ("create_account", "login"):
        username: str = args.get("username", "") or ""
        password: str = args.get("password", "") or ""

        if len(username) < 2 or len(username) > 128:
            return {
                "status": "error",
                "message": "Username must be between 2 and 128 characters.",
            }

        if len(password) < 4:
            return {
                "status": "error",
                "message": "Password must be at least 4 characters.",
            }

    elif name == "add_funds":
        amount_str: str = args.get("amount", "") or ""
        try:
            amount = Decimal(amount_str.replace(",", ""))
        except InvalidOperation:
            # Let the use case handle non-numeric; don't double-report
            return None

        if amount <= 0:
            return {
                "status": "error",
                "message": "Amount must be a positive number.",
            }

        if amount > _MAX_ADD_FUNDS_AMOUNT:
            return {
                "status": "error",
                "message": (
                    f"Amount exceeds the maximum allowed per transaction "
                    f"({_MAX_ADD_FUNDS_AMOUNT:,.0f}). "
                    "Please add funds in smaller increments."
                ),
            }

    return None
