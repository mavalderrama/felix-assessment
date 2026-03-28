import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # → backend/

# Load .env from the project root (assessment/.env), don't override existing env vars
load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-in-prod")
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() == "true"

INSTALLED_APPS = [
    "send_money.apps.SendMoneyConfig",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "send_money"),
        "USER": os.environ.get("DB_USER", "send_money"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "send_money"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# Django migrations live at backend/migrations/ (not inside the app)
MIGRATION_MODULES = {
    "send_money": "migrations",
}

# ADK DatabaseSessionService connection (SQLAlchemy + asyncpg internally)
ADK_DATABASE_URL = os.environ.get(
    "ADK_DATABASE_URL",
    "postgresql+asyncpg://send_money:send_money@localhost:5432/send_money",
)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Optional explicit model override. If unset, the agent auto-selects based
# on which API key is configured. Accepts any LiteLLM model string or a
# plain Gemini model name.
# Examples: "gemini-2.5-flash", "openai/gpt-4o", "anthropic/claude-sonnet-4-20250514"
LLM_MODEL = os.environ.get("LLM_MODEL", "")

# Langfuse observability
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")

# OTel: set to "false" in production to strip PII from traces
ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS = os.environ.get(
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "true"
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
