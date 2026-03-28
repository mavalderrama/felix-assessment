# Send Money Agent — Implementation Plan v1.0

**Date:** 2026-03-28
**Status:** Draft — pending approval
**Author:** Claude Code

---

## Context

Build a conversational **Send Money Agent** per `CHALLENGE.md` using:
- **Google ADK** (`google-adk` v1.28.0) — agent orchestration, exclusively
- **Protocol Buffers** (`google.type.Money` with `units`/`nanos` integers) — zero floating-point rounding errors for monetary values
- **PostgreSQL 18** — atomic operations via `NUMERIC(19,4)`, `SELECT FOR UPDATE`, and ADK's built-in `DatabaseSessionService`
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

### 3. Dual Database Strategy
- **ADK `DatabaseSessionService`** (`postgresql+asyncpg://...`) — manages its own tables (`sessions`, `events`, `app_states`) with row-level locking and JSONB state
- **Custom Alembic migrations** — manage domain tables (`transfers`, `corridors`) with `NUMERIC(19,4)` columns
- Both live in the same PostgreSQL 18 instance

### 4. Money Representation
```
Amount $42.99 USD  →  Money { units=42, nanos=990000000, currency_code="USD" }
Stored in PG as    →  NUMERIC(19,4): 42.9900
Python runtime     →  Decimal("42.99")
```
Conversion: `decimal_to_money_proto()` / `money_proto_to_decimal()` in `adapters/proto/converters.py`

---

## Directory Structure

```
assessment/
├── pyproject.toml
├── main.py                          # async interactive CLI entrypoint
├── docker-compose.yml               # PostgreSQL 18
├── alembic.ini
├── .env.example
│
├── docs/
│   └── plan_v1.md                   # this file
│
├── proto/
│   └── send_money/v1/
│       ├── common.proto             # DeliveryMethod, TransferStatus enums
│       └── transfer.proto           # TransferDraft, TransferConfirmation messages
│
├── src/send_money/
│   ├── __init__.py
│   ├── agent.py                     # module-level root_agent (ADK CLI compat)
│   │
│   ├── domain/                      # innermost layer — no external deps
│   │   ├── __init__.py
│   │   ├── entities.py              # Pydantic: TransferDraft
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
│   │       ├── models.py            # SQLAlchemy ORM: TransferRecord, Corridor
│   │       ├── transfer_repository.py
│   │       └── corridor_repository.py  # + in-memory simulated impl
│   │
│   └── infrastructure/              # outermost layer — frameworks and drivers
│       ├── __init__.py
│       ├── config.py                # pydantic-settings: Settings
│       ├── database.py              # async engine + session factory
│       ├── container.py             # DI container (wires all layers)
│       ├── simulated_services.py    # SimulatedExchangeRateService, SimulatedFeeService
│       └── migrations/
│           ├── env.py
│           └── versions/
│               └── 001_initial.py
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
        └── test_repository.py
```

---

## Dependencies

`pyproject.toml`:
```toml
[project]
dependencies = [
    "google-adk>=1.28.0",
    "asyncpg>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.48",
    "pydantic-settings>=2.13.0",
    "googleapis-common-protos>=1.73.0",
    "grpcio-tools>=1.78.0",
    "alembic>=1.18.0",
    "protobuf>=6.33.0",
]

[dependency-groups]
dev = [
    "mypy>=1.19.1",
    "pre-commit>=4.5.1",
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "ruff>=0.15.8",
    "aiosqlite>=0.22.0",   # in-memory SQLite for tests
]
```

---

## Protobuf Schema

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

### Session State Shape
```json
{
  "transfer_draft": {
    "id": null,
    "destination_country": "MX",
    "amount_units": 500, "amount_nanos": 0, "amount_currency": "USD",
    "beneficiary_name": "Maria Garcia",
    "delivery_method": "BANK_DEPOSIT",
    "status": "COLLECTING",
    "fee_units": null, "receive_amount_units": null
  }
}
```

---

## PostgreSQL Schema

```sql
-- Domain tables (Alembic-managed)

CREATE TABLE corridors (
    id SERIAL PRIMARY KEY,
    country_code CHAR(2) NOT NULL,
    delivery_method VARCHAR(20) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (country_code, delivery_method)
);

CREATE TABLE transfers (
    id VARCHAR(36) PRIMARY KEY,              -- UUIDv7 generated in Python
    idempotency_key VARCHAR(64) UNIQUE NOT NULL,
    destination_country CHAR(2) NOT NULL,
    amount NUMERIC(19, 4) NOT NULL CHECK (amount > 0),
    amount_currency CHAR(3) NOT NULL,
    beneficiary_name VARCHAR(255) NOT NULL,
    delivery_method VARCHAR(20) NOT NULL,
    fee NUMERIC(19, 4) NOT NULL,
    exchange_rate NUMERIC(19, 9),
    receive_amount NUMERIC(19, 4),
    receive_currency CHAR(3),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    confirmation_code VARCHAR(20),
    session_id VARCHAR(128),
    user_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ADK tables auto-created by DatabaseSessionService (sessions, events, app_states, user_states)
```

Key atomicity: `ConfirmTransferUseCase` uses `SELECT ... FOR UPDATE` on the idempotency key row to prevent duplicate submissions.

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
| 1 | Foundation | Update `pyproject.toml`, `uv sync`, create dir structure |
| 2 | Foundation | `docker-compose.yml`, `infrastructure/config.py` |
| 3 | Domain | `enums.py`, `value_objects.py`, `entities.py`, `repositories.py` |
| 4 | Protobuf | `.proto` files + `adapters/proto/converters.py` |
| 5 | Application | `ports.py`, 4 use case files |
| 6 | Infrastructure | `database.py`, `container.py`, `simulated_services.py` |
| 7 | Persistence | `adapters/persistence/models.py` + repository impls |
| 8 | Agent | `instructions.py`, `tools.py`, `agent_definition.py`, `agent.py`, `main.py` |
| 9 | Migrations | `alembic.ini`, `migrations/env.py`, `001_initial.py` |
| 10 | Testing | Unit tests (domain, use cases, tools, converters) + integration test |

---

## Verification Checklist

- [ ] `uv sync` completes without errors
- [ ] `docker compose up -d` starts PG18, health check passes
- [ ] `uv run alembic upgrade head` creates `transfers` + `corridors` tables
- [ ] `uv run python main.py` — full conversation succeeds:
  - Open-ended "I want to send money" → agent asks missing fields
  - Mid-flow correction ("change country to Colombia") → handled correctly
  - `validate_transfer` → shows fees + FX rate
  - `confirm_transfer` → returns confirmation code
- [ ] `psql -c "SELECT * FROM transfers"` — record persisted with `NUMERIC` values (no floats)
- [ ] `uv run pytest` — all tests pass
- [ ] `uv run mypy src/` — no type errors
- [ ] `uv run ruff check src/` — no lint errors

---

## Potential Pitfalls

| Risk | Mitigation |
|------|-----------|
| `google.type.Money` serializes `units` as string in JSON (`"500"` not `500`) | Handle in `dict_to_money_proto` with explicit `int()` cast |
| ADK tool functions can't take class instances directly | Use closure factory `create_tools(container)` |
| `asyncpg` not in pyproject yet | Add explicitly — ADK depends on SQLAlchemy but not asyncpg |
| PG18 `gen_random_uuid()` is UUIDv4, not v7 | Generate UUIDv7 in Python before INSERT |
| `Event.is_final_response()` does not exist in ADK v1.28 | Filter by `event.author != "user"` and non-null `event.content.parts` with text |
