# Send Money Agent — Implementation Plan v4.0

**Date:** 2026-03-28
**Status:** Draft — pending approval
**Author:** Claude Code
**Changes from v3:** All backend logic moved under `backend/` folder.

---

## Context

Build a conversational **Send Money Agent** per `CHALLENGE.md` using:
- **Google ADK** (`google-adk` v1.28.0) — agent orchestration, exclusively
- **Protocol Buffers** (`google.type.Money` with `units`/`nanos` integers) — zero floating-point rounding errors for monetary values
- **PostgreSQL 18** — atomic operations via `NUMERIC(19,4)`, `SELECT FOR UPDATE`, and ADK's built-in `DatabaseSessionService`
- **Django** — ORM, migrations, settings, and admin for domain tables
- **Langfuse** (self-hosted) — observability, tracing, and auditability for every agent interaction
- **Clean Architecture** + mandatory DI per `CLAUDE.md`

---

## Design Decisions

Unchanged from v3. See plan_v3.md for rationale on:
1. Single agent with tools (not multi-agent transfer)
2. Protobuf as schema contract, Pydantic as runtime
3. Dual ORM strategy (ADK→SQLAlchemy, domain→Django)
4. Django as framework layer (ORM + migrations + settings only, no web)
5. Money representation (Decimal ↔ google.type.Money ↔ NUMERIC)
6. Langfuse via OTLP bridge + custom BasePlugin

---

## Directory Structure

```
assessment/
├── pyproject.toml                   # Python project — stays at root
├── docker-compose.yml               # PG18 + Langfuse stack — stays at root
├── .env.example
│
├── docs/
│   ├── plan_v1.md
│   ├── plan_v2.md
│   ├── plan_v3.md
│   └── plan_v4.md                   # this file
│
└── backend/                         # ALL backend logic lives here
    ├── manage.py                    # Django management script
    ├── main.py                      # async interactive CLI entrypoint
    │
    ├── config/                      # Django project config
    │   ├── __init__.py
    │   ├── settings.py              # DB, Langfuse, installed apps
    │   └── asgi.py
    │
    ├── proto/
    │   └── send_money/v1/
    │       ├── common.proto         # DeliveryMethod, TransferStatus enums
    │       └── transfer.proto       # TransferDraft, TransferConfirmation messages
    │
    ├── send_money/
    │   ├── __init__.py
    │   ├── agent.py                 # module-level root_agent (ADK CLI compat)
    │   │
    │   ├── domain/                  # innermost layer — no external deps
    │   │   ├── __init__.py
    │   │   ├── entities.py          # Pydantic: TransferDraft
    │   │   ├── value_objects.py     # Money (Decimal ↔ google.type.Money)
    │   │   ├── enums.py             # DeliveryMethod, TransferStatus, Country
    │   │   ├── repositories.py      # ABCs: TransferRepository, CorridorRepository
    │   │   └── errors.py
    │   │
    │   ├── application/             # use cases — depends on domain only
    │   │   ├── __init__.py
    │   │   ├── ports.py             # ABCs: ExchangeRateService, FeeService
    │   │   └── use_cases/
    │   │       ├── __init__.py
    │   │       ├── collect_transfer_details.py
    │   │       ├── validate_transfer.py
    │   │       ├── confirm_transfer.py
    │   │       └── get_corridors.py
    │   │
    │   ├── adapters/                # interface adapters
    │   │   ├── __init__.py
    │   │   ├── agent/
    │   │   │   ├── __init__.py
    │   │   │   ├── agent_definition.py
    │   │   │   ├── tools.py
    │   │   │   └── instructions.py
    │   │   ├── proto/
    │   │   │   ├── __init__.py
    │   │   │   └── converters.py    # Decimal ↔ Money proto ↔ dict
    │   │   ├── observability/
    │   │   │   ├── __init__.py
    │   │   │   ├── otel_setup.py    # OTLP exporter → Langfuse
    │   │   │   └── langfuse_plugin.py  # LangfuseAuditPlugin(BasePlugin)
    │   │   └── persistence/
    │   │       ├── __init__.py
    │   │       ├── django_models.py
    │   │       ├── transfer_repository.py
    │   │       └── corridor_repository.py
    │   │
    │   └── infrastructure/          # outermost layer
    │       ├── __init__.py
    │       ├── container.py         # DI container
    │       ├── simulated_services.py
    │       └── management/
    │           └── commands/
    │               └── seed_corridors.py
    │
    ├── migrations/                  # Django migrations
    │   ├── __init__.py
    │   └── 0001_initial.py
    │
    └── tests/
        ├── __init__.py
        ├── conftest.py
        ├── unit/
        │   ├── domain/
        │   │   ├── test_entities.py
        │   │   └── test_value_objects.py
        │   ├── application/
        │   │   └── test_use_cases.py
        │   └── adapters/
        │       ├── test_converters.py
        │       ├── test_tools.py
        │       └── test_langfuse_plugin.py
        └── integration/
            ├── test_agent_flow.py
            └── test_repository.py
```

---

## Affected Path Updates

All internal references shift from the previous layout. Key changes:

| Concern | v3 path | v4 path |
|---------|---------|---------|
| Django entrypoint | `manage.py` | `backend/manage.py` |
| CLI entrypoint | `main.py` | `backend/main.py` |
| Django settings | `config/settings.py` | `backend/config/settings.py` |
| Django settings module | `config.settings` | `backend.config.settings` |
| Proto files | `proto/send_money/v1/` | `backend/proto/send_money/v1/` |
| Domain layer | `src/send_money/domain/` | `backend/send_money/domain/` |
| Application layer | `src/send_money/application/` | `backend/send_money/application/` |
| Adapters layer | `src/send_money/adapters/` | `backend/send_money/adapters/` |
| Infrastructure layer | `src/send_money/infrastructure/` | `backend/send_money/infrastructure/` |
| ADK module root | `src/send_money/agent.py` | `backend/send_money/agent.py` |
| Django migrations | `migrations/` | `backend/migrations/` |
| Tests | `tests/` | `backend/tests/` |
| Installed apps | `"src.send_money"` | `"send_money"` |

---

## `pyproject.toml` path config

Since `backend/` is not a package root, we configure the Python path so imports resolve correctly:

```toml
[project]
dependencies = [
    "google-adk>=1.28.0",
    "django>=5.2",
    "psycopg[binary]>=3.2.0",
    "googleapis-common-protos>=1.73.0",
    "grpcio-tools>=1.78.0",
    "protobuf>=6.33.0",
    "langfuse>=2.60.0",
    "opentelemetry-sdk>=1.33.0",
    "opentelemetry-exporter-otlp-proto-http>=1.33.0",
]

[dependency-groups]
dev = [
    "mypy>=1.19.1",
    "pre-commit>=4.5.1",
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "pytest-django>=4.11.0",
    "ruff>=0.15.8",
]

[tool.pytest.ini_options]
testpaths = ["backend/tests"]
pythonpath = ["backend"]
DJANGO_SETTINGS_MODULE = "config.settings"

[tool.mypy]
mypy_path = "backend"

[tool.ruff]
src = ["backend"]
```

Setting `pythonpath = ["backend"]` means `import send_money`, `import config` resolve without any prefix — clean, idiomatic Django.

---

## Django Settings (updated path)

**`backend/config/settings.py`**
```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # → backend/

INSTALLED_APPS = [
    "send_money",   # no "src." prefix — backend/ is on sys.path
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "send_money"),
        "USER": os.environ.get("DB_USER", "send_money"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "send_money_dev"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

ADK_DATABASE_URL = os.environ.get(
    "ADK_DATABASE_URL",
    "postgresql+asyncpg://send_money:send_money_dev@localhost:5432/send_money",
)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")

ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS = os.environ.get(
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "true"
)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() == "true"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
```

---

## DI Container (updated paths)

**`backend/send_money/infrastructure/container.py`**
```python
import os
import django

class Container:
    def __init__(self):
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()
        # all ORM imports happen after setup() ...
```

---

## Proto Compilation Command (updated path)

```bash
cd backend
python -m grpc_tools.protoc \
  -I proto \
  -I ../.venv/lib/python3.14/site-packages \
  --python_out=send_money/adapters/proto \
  proto/send_money/v1/*.proto
```

---

## manage.py (updated)

**`backend/manage.py`**
```python
#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
```

Run from repo root: `python backend/manage.py migrate`
Or from inside backend: `cd backend && python manage.py migrate`

---

## docker-compose.yml

Unchanged from v3 — lives at repo root, no path adjustments needed.

---

## Implementation Order

| # | Phase | What |
|---|-------|------|
| 1 | Foundation | Update `pyproject.toml` (deps + `pythonpath = ["backend"]`), `uv sync` |
| 2 | Foundation | Create `backend/` tree, `docker-compose.yml`, `backend/config/settings.py`, `backend/manage.py` |
| 3 | Domain | `backend/send_money/domain/` — enums, value objects, entities, repositories, errors |
| 4 | Protobuf | `backend/proto/send_money/v1/` + `backend/send_money/adapters/proto/converters.py` |
| 5 | Application | `backend/send_money/application/` — ports + 4 use cases |
| 6 | Django Models | `backend/send_money/adapters/persistence/django_models.py`, `python backend/manage.py makemigrations`, `migrate` |
| 7 | Persistence | `transfer_repository.py`, `corridor_repository.py` |
| 8 | Observability | `backend/send_money/adapters/observability/otel_setup.py` + `langfuse_plugin.py` |
| 9 | Infrastructure | `backend/send_money/infrastructure/container.py` + `simulated_services.py` |
| 10 | Agent | `instructions.py`, `tools.py`, `agent_definition.py`, `backend/send_money/agent.py`, `backend/main.py` |
| 11 | Testing | `backend/tests/` — unit + integration tests |

---

## Verification Checklist

- [ ] `uv sync` completes without errors
- [ ] `docker compose up -d` starts all 6 containers (PG18 + Langfuse stack)
- [ ] `python backend/manage.py migrate` creates `transfers` + `corridors` tables
- [ ] `python backend/manage.py seed_corridors` populates corridor data
- [ ] `uv run python backend/main.py` — full conversation succeeds:
  - Open-ended "I want to send money" → agent asks missing fields
  - Mid-flow correction ("change country to Colombia") → handled correctly
  - `validate_transfer` → shows fees + FX rate
  - `confirm_transfer` → returns confirmation code
- [ ] Langfuse trace visible at `http://localhost:3000` with nested spans + scores
- [ ] `uv run pytest` — all tests pass
- [ ] `uv run mypy backend/` — no type errors
- [ ] `uv run ruff check backend/` — no lint errors

---

## Changes from v3

| Aspect | v3 | v4 |
|--------|----|----|
| Backend root | `src/send_money/`, `config/`, `migrations/`, `tests/`, `proto/` scattered at repo root | All under `backend/` |
| Python import root | `src/` on sys.path → `from send_money...` | `backend/` on sys.path → `from send_money...` (same imports, different root) |
| Django app name in `INSTALLED_APPS` | `"src.send_money"` | `"send_money"` |
| `manage.py` location | repo root | `backend/manage.py` |
| `main.py` location | repo root | `backend/main.py` |
| `pyproject.toml` | No `pythonpath` config | `pythonpath = ["backend"]` in `[tool.pytest.ini_options]`; `mypy_path`, `ruff src` |
| Proto compilation | `python -m grpc_tools.protoc -I proto ...` from root | `cd backend && python -m grpc_tools.protoc -I proto ...` |
| `pyproject.toml` itself | repo root | repo root (unchanged) |
| `docker-compose.yml` | repo root | repo root (unchanged) |
| `docs/` | repo root | repo root (unchanged) |
