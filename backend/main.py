"""Interactive CLI entrypoint for the Send Money Agent.

Usage:
    uv run python backend/main.py

Environment variables (see .env.example):
    GOOGLE_API_KEY, DB_*, ADK_DATABASE_URL, LANGFUSE_*, DJANGO_*
"""
from __future__ import annotations

import asyncio
import os
import sys

# Ensure backend/ is on sys.path when run as `python backend/main.py`
sys.path.insert(0, os.path.dirname(__file__))

from google.adk import Runner
from google.genai import types

from send_money.infrastructure.container import Container


async def main() -> None:
    container = Container()
    session_service = container.create_session_service()
    app = container.create_app()

    runner = Runner(app=app, session_service=session_service)

    session = await session_service.create_session(
        app_name="send_money",
        user_id="cli_user",
        state={"transfer_draft": {}},
    )

    print("Send Money Agent — type 'quit' to exit\n")
    print(f"Session ID: {session.id}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        if not user_input:
            continue

        content = types.Content(
            role="user",
            parts=[types.Part(text=user_input)],
        )

        async for event in runner.run_async(
            user_id="cli_user",
            session_id=session.id,
            new_message=content,
        ):
            # Filter to agent text responses only (skip tool call events)
            if (
                event.author != "user"
                and event.content
                and event.content.parts
                and not event.content.parts[0].function_call
                and not event.content.parts[0].function_response
            ):
                text = "".join(
                    p.text for p in event.content.parts if hasattr(p, "text") and p.text
                )
                if text:
                    print(f"\nAgent: {text}\n")


if __name__ == "__main__":
    asyncio.run(main())
