# Send Money Agent — Implementation Plan v2.0

**Date:** 2026-03-28
**Status:** Draft — pending approval
**Author:** Claude Code
**Changes from v1:** Replaced SQLAlchemy/Alembic/pydantic-settings with Django ORM, Django migrations, and Django settings.

---

## Context

Build a conversational **Send Money Agent** per `CHALLENGE.md` using:
- **Google ADK** (`google-adk` v1.28.0) — agent orchestration, exclusively
- **Protocol Buffers** (`google.type.Money` with `units`/`nanos` integers) — zero floating-point rounding errors for monetary values
- **PostgreSQL 18** — atomic operations via `NUMERIC(19,4)`, `SELECT FOR UPDATE`, and ADK's built-in `DatabaseSessionService`
- **Django** — ORM, migrations, settings, and admin for domain tables
- **Clean Architecture** + mandatory DI per `CLAUDE.md`

---

## Design Decisions

### 1. Single Agent with Tools (not multi-agent transfer)
The challenge requires mid-flow corrections ("change the country"). A single `LlmAgent` with state-mutating tools handles any field in any order naturally. Multi-agent `transfer_to_agent` would create a rigid pipeline that fights corrections.

### 2. Protobuf as Schema Contract, Pydantic as Runtime
- `.proto` files define the canonical domain schema
- `google.type.Money` (int64 `units` + int32 `nanos`) is lossless — no floats ever touch monetary values
- Pydantic models are the runtime domain entities, hydrated from/to dicts via converters
- ADK session state stores the transfer draft as a JSON-safe dict via `MessageToDict`/`model_dump`

### 3. Dual ORM Strategy
- **ADK `DatabaseSessionService`** — internally uses SQLAlchemy (we just pass it the PG URL). Manages its own tables (`sessions`, `events`, `app_states`, `user_states`). We don't control this.
- **Django ORM** — manages all domain tables (`transfers`, `corridors`) via Django models and migrations. Uses `DecimalField` (maps to PG `NUMERIC`) for money columns.
- Both share the same PostgreSQL 18 instance. ADK auto-creates its tables; Django manages ours via `python manage.py migrate`.

### 4. Django as Framework Layer
- Django settings module for configuration (DB URL, API keys, app config)
- Django ORM for domain persistence (async via `sync_to_async` or Django 5.x async ORM)
- Django migrations instead of Alembic
- Django management commands for seeding corridor data
- Django admin (optional) for inspecting transfers/corridors during development
- **Not using Django views/URLs/middleware** — this is a CLI agent, not a web app

### 5. Money Representation
```
Amount $42.99 USD  →  Money { units=42, nanos=990000000, currency_code="USD" }
Stored in PG as    →  Django DecimalField / NUMERIC(19,4): 42.9900
Python runtime     →  Decimal("42.99")
```
Conversion: `decimal_to_money_proto()` / `money_proto_to_decimal()` in `adapters/proto/converters.py`

---

## Directory Structure

```
assessment/
├── pyproject.toml
├── manage.py                        # Django management script
├── main.py                          # async interactive CLI entrypoint
├── docker-compose.yml               # PostgreSQL 18
├── .env.example
│
├── docs/
│   ├── plan_v1.md                   # previous version
│   └── plan_v2.md                   # this file
│
├── proto/
│   └── send_money/v1/
│       ├── common.proto             # DeliveryMethod, TransferStatus enums
│       └── transfer.proto           # TransferDraft, TransferConfirmation messages
│
├── config/                          # Django project config
│   ├── __init__.py
│   ├── settings.py                  # Django settings (DB, installed apps, etc.)
│   └── asgi.py                      # ASGI config (for potential future web use)
│
├── src/send_money/
│   ├── __init__.py
│   ├── agent.py                     # module-level root_agent (ADK CLI compat)
│   │
│   ├── domain/                      # innermost layer — no external deps
│   │   ├── __init__.py
│   │   ├── entities.py              # Pydantic: TransferDraft (runtime domain entity)
│   │   ├── value_objects.py         # Money value object (Decimal ↔ google.type.Money)
│   │   ├── enums.py                 # DeliveryMethod, TransferStatus, Country
│   │   ├── repositories.py          # ABCs: TransferRepository, CorridorRepository
│   │   └── errors.py               # Domain exceptions
│   │
│   ├── application/                 # use cases — depends on domain only
│   │   ├── __init__.py
│   │   ├── ports.py                 # ABCs: ExchangeRateService, FeeService
│   │   └── use_cases/
│   │       ├── __init__.py
│   │       ├── collect_transfer_details.py
│   │       ├── validate_transfer.py
│   │       ├── confirm_transfer.py
│   │       └── get_corridors.py
│   │
│   ├── adapters/                    # interface adapters — bridges domain ↔ frameworks
│   │   ├── __init__.py
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   ├── agent_definition.py  # create_send_money_agent(container) -> Agent
│   │   │   ├── tools.py             # create_tools(container) -> list[Callable]
│   │   │   └── instructions.py      # SEND_MONEY_INSTRUCTION with {transfer_draft}
│   │   ├── proto/
│   │   │   ├── __init__.py
│   │   │   └── converters.py        # Decimal ↔ Money proto ↔ dict
│   │   └── persistence/
│   │       ├── __init__.py
│   │       ├── django_models.py     # Django ORM models: TransferRecord, Corridor
│   │       ├── transfer_repository.py  # DjangoTransferRepository (implements ABC)
│   │       └── corridor_repository.py  # DjangoCorridorRepository + InMemoryCorridorRepository
│   │
│   └── infrastructure/              # outermost layer — frameworks and drivers
│       ├── __init__.py
│       ├── container.py             # DI container (wires all layers)
│       ├── simulated_services.py    # SimulatedExchangeRateService, SimulatedFeeService
│       └── management/
│           └── commands/
│               └── seed_corridors.py  # Django management command to seed corridor data
│
├── migrations/                      # Django migrations for send_money app
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
    │       └── test_tools.py
    └── integration/
        ├── test_agent_flow.py       # full conversation with InMemorySessionService
        └── test_repository.py       # Django TestCase with test DB
```

---

## Dependencies

`pyproject.toml`:
```toml
[project]
dependencies = [
    "google-adk>=1.28.0",
    "django>=5.2",
    "psycopg[binary]>=3.2.0",       # Django's async PG driver
    "googleapis-common-protos>=1.73.0",
    "grpcio-tools>=1.78.0",
    "protobuf>=6.33.0",
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
```

**Key dependency changes from v1:**
- **Added:** `django>=5.2`, `psycopg[binary]>=3.2.0` (Django's recommended async PG driver), `pytest-django`
- **Removed:** `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`, `aiosqlite`
- Note: ADK internally depends on SQLAlchemy — that stays as a transitive dep for `DatabaseSessionService` only. We don't use it directly.
- Note: ADK's `DatabaseSessionService` needs asyncpg for its PG connection. It's pulled in transitively by `google-adk`, but we add `psycopg[binary]` for Django's own PG connection.

---

## Django Settings

**`config/settings.py`**
```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() == "true"

INSTALLED_APPS = [
    "src.send_money",
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

# ADK DatabaseSessionService URL (uses asyncpg via SQLAlchemy internally)
ADK_DATABASE_URL = os.environ.get(
    "ADK_DATABASE_URL",
    "postgresql+asyncpg://send_money:send_money_dev@localhost:5432/send_money"
)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
```

---

## Django Models

**`src/send_money/adapters/persistence/django_models.py`**
```python
from django.db import models
from decimal import Decimal

class Corridor(models.Model):
    country_code = models.CharField(max_length=2)
    delivery_method = models.CharField(max_length=20)
    currency_code = models.CharField(max_length=3)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "corridors"
        unique_together = ("country_code", "delivery_method")

class TransferRecord(models.Model):
    id = models.CharField(max_length=36, primary_key=True)  # UUIDv7 from Python
    idempotency_key = models.CharField(max_length=64, unique=True)
    destination_country = models.CharField(max_length=2)
    amount = models.DecimalField(max_digits=19, decimal_places=4)  # NUMERIC(19,4)
    amount_currency = models.CharField(max_length=3)
    beneficiary_name = models.CharField(max_length=255)
    delivery_method = models.CharField(max_length=20)
    fee = models.DecimalField(max_digits=19, decimal_places=4)
    exchange_rate = models.DecimalField(max_digits=19, decimal_places=9, null=True)
    receive_amount = models.DecimalField(max_digits=19, decimal_places=4, null=True)
    receive_currency = models.CharField(max_length=3, blank=True)
    status = models.CharField(max_length=20, default="PENDING")
    confirmation_code = models.CharField(max_length=20, blank=True)
    session_id = models.CharField(max_length=128, blank=True)
    user_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transfers"
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=Decimal("0")),
                name="transfer_amount_positive",
            ),
        ]
```

---

## Django Repository Implementations

**`src/send_money/adapters/persistence/transfer_repository.py`**
```python
from asgiref.sync import sync_to_async
from django.db import transaction
from ..persistence.django_models import TransferRecord
from ...domain.repositories import TransferRepository
from ...domain.entities import TransferDraft

class DjangoTransferRepository(TransferRepository):
    async def save(self, draft: TransferDraft) -> TransferDraft:
        @sync_to_async
        def _save():
            with transaction.atomic():
                # SELECT FOR UPDATE via select_for_update() for idempotency
                record, created = TransferRecord.objects.select_for_update().get_or_create(
                    idempotency_key=draft.idempotency_key,
                    defaults={...}  # map draft fields to model fields
                )
                return self._to_entity(record)
        return await _save()

    async def get_by_id(self, transfer_id: str) -> TransferDraft | None:
        @sync_to_async
        def _get():
            try:
                record = TransferRecord.objects.get(id=transfer_id)
                return self._to_entity(record)
            except TransferRecord.DoesNotExist:
                return None
        return await _get()
```

Key: Django's `select_for_update()` + `transaction.atomic()` gives us the same `SELECT FOR UPDATE` atomicity as raw SQL.

---

## Protobuf Schema

(Unchanged from v1)

**`proto/send_money/v1/common.proto`**
```protobuf
syntax = "proto3";
package send_money.v1;

enum DeliveryMethod {
  DELIVERY_METHOD_UNSPECIFIED = 0;
  BANK_DEPOSIT = 1;
  MOBILE_WALLET = 2;
  CASH_PICKUP = 3;
}

enum TransferStatus {
  TRANSFER_STATUS_UNSPECIFIED = 0;
  COLLECTING = 1;
  VALIDATING = 2;
  CONFIRMED = 3;
  FAILED = 4;
}
```

**`proto/send_money/v1/transfer.proto`**
```protobuf
syntax = "proto3";
package send_money.v1;

import "google/type/money.proto";
import "send_money/v1/common.proto";

message TransferDraft {
  string id = 1;
  string destination_country = 2;       // ISO 3166-1 alpha-2
  google.type.Money amount = 3;          // source amount — units/nanos, no float
  string beneficiary_name = 4;
  string beneficiary_id = 5;
  DeliveryMethod delivery_method = 6;
  TransferStatus status = 7;
  string source_currency = 8;
  string destination_currency = 9;
  google.type.Money fee = 10;
  google.type.Money receive_amount = 11;
}

message TransferConfirmation {
  string transfer_id = 1;
  string confirmation_code = 2;
  TransferDraft draft = 3;
}
```

Compile with:
```bash
python -m grpc_tools.protoc \
  -I proto \
  -I .venv/lib/python3.14/site-packages \
  --python_out=src/send_money/adapters/proto \
  proto/send_money/v1/*.proto
```

---

## Agent Design

(Unchanged from v1)

### Instructions (key excerpt)
```python
SEND_MONEY_INSTRUCTION = """
You are a Send Money Agent helping users initiate international wire transfers.

Current transfer state:
{transfer_draft}

REQUIRED FIELDS (all must be provided before validation):
- destination_country  (supported: MX, CO, GT, PH, IN, GB)
- amount + currency    (e.g. "500 USD")
- beneficiary_name     (full name of the recipient)
- delivery_method      (BANK_DEPOSIT, MOBILE_WALLET, CASH_PICKUP)

WORKFLOW:
1. Ask for missing fields conversationally — never ask for what is already set.
2. Call update_transfer_field() for each piece of information gathered.
3. Once all required fields are present, call validate_transfer().
4. Present the fee/exchange-rate summary, ask user to confirm.
5. On confirmation, call confirm_transfer() and display the confirmation code.
6. If the user wants to change a field at any point, call update_transfer_field()
   and re-validate.
"""
```

### Tools (closures over use cases via `create_tools(container)`)

| Tool | State mutation | Use case called |
|------|---------------|-----------------|
| `update_transfer_field(field_name, field_value)` | Sets `state["transfer_draft"][field]` | `CollectTransferDetailsUseCase` |
| `validate_transfer()` | Sets fees, FX, receive_amount in draft | `ValidateTransferUseCase` |
| `confirm_transfer()` | Persists to `transfers` table | `ConfirmTransferUseCase` |
| `get_supported_countries()` | Read-only | `GetCorridorsUseCase` |
| `get_delivery_methods(country)` | Read-only | `GetCorridorsUseCase` |

### Agent Definition
```python
Agent(
    name="send_money_agent",
    model="gemini-2.5-flash",
    instruction=SEND_MONEY_INSTRUCTION,
    tools=create_tools(container),
    output_key="agent_response",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
```

---

## DI Container

**`src/send_money/infrastructure/container.py`**
```python
import django
import os

class Container:
    def __init__(self):
        # Ensure Django is initialized before using ORM
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()

        from ..adapters.persistence.transfer_repository import DjangoTransferRepository
        from ..adapters.persistence.corridor_repository import DjangoCorridorRepository
        from .simulated_services import SimulatedExchangeRateService, SimulatedFeeService
        from ..application.use_cases.collect_transfer_details import CollectTransferDetailsUseCase
        from ..application.use_cases.validate_transfer import ValidateTransferUseCase
        from ..application.use_cases.confirm_transfer import ConfirmTransferUseCase
        from ..application.use_cases.get_corridors import GetCorridorsUseCase

        # Repositories
        self.corridor_repository = DjangoCorridorRepository()
        self.transfer_repository = DjangoTransferRepository()

        # Simulated services
        self.exchange_rate_service = SimulatedExchangeRateService()
        self.fee_service = SimulatedFeeService()

        # Use cases (constructor-injected dependencies)
        self.collect_uc = CollectTransferDetailsUseCase(self.corridor_repository)
        self.validate_uc = ValidateTransferUseCase(
            self.corridor_repository, self.exchange_rate_service, self.fee_service
        )
        self.confirm_uc = ConfirmTransferUseCase(self.transfer_repository)
        self.corridors_uc = GetCorridorsUseCase(self.corridor_repository)

    def create_session_service(self):
        from django.conf import settings
        from google.adk.sessions import DatabaseSessionService
        return DatabaseSessionService(settings.ADK_DATABASE_URL)

    def create_agent(self):
        from ..adapters.agent.agent_definition import create_send_money_agent
        return create_send_money_agent(self)
```

---

## docker-compose.yml

```yaml
services:
  postgres:
    image: postgres:18
    environment:
      POSTGRES_DB: send_money
      POSTGRES_USER: send_money
      POSTGRES_PASSWORD: send_money_dev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U send_money -d send_money"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

---

## Implementation Order

| # | Phase | What |
|---|-------|------|
| 1 | Foundation | Update `pyproject.toml` (add Django, psycopg, remove SQLAlchemy/Alembic), `uv sync` |
| 2 | Foundation | Create dir structure, `docker-compose.yml`, `config/settings.py`, `manage.py` |
| 3 | Domain | `enums.py`, `value_objects.py`, `entities.py`, `repositories.py`, `errors.py` |
| 4 | Protobuf | `.proto` files + `adapters/proto/converters.py` |
| 5 | Application | `ports.py`, 4 use case files |
| 6 | Django Models | `adapters/persistence/django_models.py`, `python manage.py makemigrations`, `migrate` |
| 7 | Persistence | `transfer_repository.py`, `corridor_repository.py` (Django ORM impls) |
| 8 | Infrastructure | `container.py`, `simulated_services.py`, `seed_corridors` management command |
| 9 | Agent | `instructions.py`, `tools.py`, `agent_definition.py`, `agent.py`, `main.py` |
| 10 | Testing | Unit tests (domain, use cases, tools, converters) + integration tests (pytest-django) |

---

## Verification Checklist

- [ ] `uv sync` completes without errors
- [ ] `docker compose up -d` starts PG18, health check passes
- [ ] `python manage.py migrate` creates `transfers` + `corridors` tables
- [ ] `python manage.py seed_corridors` populates corridor data
- [ ] `uv run python main.py` — full conversation succeeds:
  - Open-ended "I want to send money" → agent asks missing fields
  - Mid-flow correction ("change country to Colombia") → handled correctly
  - `validate_transfer` → shows fees + FX rate
  - `confirm_transfer` → returns confirmation code
- [ ] `python manage.py shell -c "from src.send_money.adapters.persistence.django_models import TransferRecord; print(TransferRecord.objects.all())"` — record persisted with Decimal values
- [ ] `uv run pytest` — all tests pass
- [ ] `uv run mypy src/` — no type errors
- [ ] `uv run ruff check src/` — no lint errors

---

## Potential Pitfalls

| Risk | Mitigation |
|------|-----------|
| ADK's `DatabaseSessionService` requires SQLAlchemy+asyncpg internally | We don't fight this — pass it the `postgresql+asyncpg://` URL. Django uses `psycopg` for its own PG connection. Two drivers, one database. |
| Django ORM is sync-first; ADK tools are async | Use `sync_to_async` wrappers in repository implementations for Django ORM queries |
| `django.setup()` must be called before any ORM import | Container's `__init__` calls `django.setup()` first; all model imports happen after |
| `google.type.Money` serializes `units` as string in JSON (`"500"` not `500`) | Handle in `dict_to_money_proto` with explicit `int()` cast |
| ADK tool functions can't take class instances directly | Use closure factory `create_tools(container)` |
| PG18 `gen_random_uuid()` is UUIDv4, not v7 | Generate UUIDv7 in Python before INSERT |
| `Event.is_final_response()` does not exist in ADK v1.28 | Filter by `event.author != "user"` and non-null `event.content.parts` with text |
| pytest-django needs `DJANGO_SETTINGS_MODULE` | Set in `conftest.py` or `pyproject.toml` `[tool.pytest.ini_options]` |

---

## Changes from v1

| Aspect | v1 | v2 |
|--------|----|----|
| Domain ORM | SQLAlchemy async | Django ORM + `sync_to_async` |
| Migrations | Alembic | `python manage.py migrate` |
| Settings | pydantic-settings | `config/settings.py` (Django) |
| PG driver (domain) | asyncpg | psycopg3 |
| PG driver (ADK sessions) | asyncpg (unchanged) | asyncpg (unchanged) |
| Test framework | pytest + aiosqlite | pytest-django |
| Admin/debug | None | Django admin (optional) |
| Seed data | Raw SQL in Alembic migration | Django management command |
