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

from send_money.domain.errors import AuthenticationError, UsernameAlreadyExistsError
from send_money.infrastructure.container import Container


async def _authenticate(container: Container) -> str:
    """Prompt for login or account creation. Returns the authenticated user_id."""
    print("━━━ Send Money — Account ━━━━━━━━━━━━━━━━━━━")
    print("  1. Create a new account")
    print("  2. Log in to existing account")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    while True:
        choice = input("Choose (1/2): ").strip()
        if choice in ("1", "2"):
            break
        print("Please enter 1 or 2.")

    username = input("Username: ").strip()
    password = input("Password: ").strip()

    if choice == "1":
        while True:
            try:
                account = await container.create_account_uc.execute(username, password)
                print(f"\nAccount created! Welcome, {account.username}.\n")
                return account.id or ""
            except UsernameAlreadyExistsError as exc:
                print(f"Error: {exc}")
                username = input("Choose a different username: ").strip()
    else:
        while True:
            try:
                account = await container.login_uc.execute(username, password)
                print(f"\nWelcome back, {account.username}!\n")
                return account.id or ""
            except AuthenticationError:
                print("Invalid username or password. Try again.")
                username = input("Username: ").strip()
                password = input("Password: ").strip()


async def main() -> None:
    container = Container()

    user_id = await _authenticate(container)

    session_service = container.create_session_service()
    app = container.create_app()

    runner = Runner(app=app, session_service=session_service)

    session = await session_service.create_session(
        app_name="send_money",
        user_id=user_id,
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
            user_id=user_id,
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
