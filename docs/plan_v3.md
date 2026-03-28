# Send Money Agent — Implementation Plan v3.0

**Date:** 2026-03-28
**Status:** Draft — pending approval
**Author:** Claude Code
**Changes from v2:** Added Langfuse observability layer via ADK's native OpenTelemetry integration + docker-compose services for self-hosted Langfuse.

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

### 6. Langfuse Observability via OTLP (NEW in v3)

ADK v1.28 has **first-class OpenTelemetry tracing** built in (`google.adk.telemetry`). It already emits spans for:
- Agent invocations (`invoke_agent` with `gen_ai.agent.name`, `gen_ai.conversation.id`)
- LLM calls (`call_llm` with model, input/output token counts, finish reason, content)
- Tool executions (`execute_tool` with tool name, arguments, response)

Langfuse v3 accepts OpenTelemetry traces via its OTLP endpoint. This means **zero custom instrumentation code** — we configure the OTLP exporter to point at Langfuse, and all ADK traces flow in automatically.

**Integration approach: OTLP bridge (primary) + custom BasePlugin (supplementary)**

| Layer | What it captures | How |
|-------|-----------------|-----|
| **OTLP bridge** | All LLM calls, tool calls, agent invocations, token usage | ADK's built-in OTel → Langfuse OTLP endpoint. Zero custom code. |
| **Custom plugin** | Transfer-specific metadata (amount, country, status), session context, audit scores | `LangfuseAuditPlugin(BasePlugin)` using Langfuse Python SDK for scores/metadata |

**Why not SDK-only?** ADK already instruments everything via OTel. Duplicating that in a plugin would be redundant. The plugin adds only what OTel can't: domain-specific metadata and evaluation scores.

**PII control:** ADK respects `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false` to suppress prompt/response content from spans — critical for banking compliance.

---

## Directory Structure

```
assessment/
├── pyproject.toml
├── manage.py                        # Django management script
├── main.py                          # async interactive CLI entrypoint
├── docker-compose.yml               # PG18 + Langfuse stack
├── .env.example
│
├── docs/
│   ├── plan_v1.md
│   ├── plan_v2.md
│   └── plan_v3.md                   # this file
│
├── proto/
│   └── send_money/v1/
│       ├── common.proto             # DeliveryMethod, TransferStatus enums
│       └── transfer.proto           # TransferDraft, TransferConfirmation messages
│
├── config/                          # Django project config
│   ├── __init__.py
│   ├── settings.py                  # Django settings (DB, Langfuse, installed apps)
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
│   │   ├── observability/           # NEW — Langfuse integration
│   │   │   ├── __init__.py
│   │   │   ├── otel_setup.py        # configure OTLP exporter → Langfuse
│   │   │   └── langfuse_plugin.py   # LangfuseAuditPlugin(BasePlugin) for domain metadata
│   │   └── persistence/
│   │       ├── __init__.py
│   │       ├── django_models.py     # Django ORM models: TransferRecord, Corridor
│   │       ├── transfer_repository.py
│   │       └── corridor_repository.py
│   │
│   └── infrastructure/              # outermost layer — frameworks and drivers
│       ├── __init__.py
│       ├── container.py             # DI container (wires all layers + observability)
│       ├── simulated_services.py    # SimulatedExchangeRateService, SimulatedFeeService
│       └── management/
│           └── commands/
│               └── seed_corridors.py
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
    │       ├── test_tools.py
    │       └── test_langfuse_plugin.py   # NEW
    └── integration/
        ├── test_agent_flow.py
        └── test_repository.py
```

---

## Dependencies

`pyproject.toml`:
```toml
[project]
dependencies = [
    "google-adk>=1.28.0",
    "django>=5.2",
    "psycopg[binary]>=3.2.0",
    "googleapis-common-protos>=1.73.0",
    "grpcio-tools>=1.78.0",
    "protobuf>=6.33.0",
    # Observability
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
```

**New in v3:** `langfuse`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`

---

## Observability Architecture

### OTLP Bridge: Zero-Code Tracing

**`src/send_money/adapters/observability/otel_setup.py`**

```python
import base64
import os

from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from google.adk.telemetry.setup import OTelHooks, maybe_set_otel_providers


def setup_langfuse_otel(
    langfuse_host: str,
    public_key: str,
    secret_key: str,
) -> None:
    """Configure ADK's OTel pipeline to export traces to Langfuse via OTLP."""
    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()

    exporter = OTLPSpanExporter(
        endpoint=f"{langfuse_host}/api/public/otel/v1/traces",
        headers={"Authorization": f"Basic {auth}"},
    )

    hooks = OTelHooks(
        span_processors=[BatchSpanProcessor(exporter)],
    )
    maybe_set_otel_providers(otel_hooks_to_setup=[hooks])
```

This gives us **automatic tracing** of:
- Every `invoke_agent` call (agent name, session ID, conversation ID)
- Every `call_llm` call (model, input/output tokens, thinking tokens, finish reason, content)
- Every `execute_tool` call (tool name, arguments, response, errors)
- Nested span hierarchy showing the full agent → LLM → tool flow

### Custom Plugin: Domain-Specific Audit Metadata

**`src/send_money/adapters/observability/langfuse_plugin.py`**

```python
from google.adk.plugins.base_plugin import BasePlugin
from langfuse import Langfuse


class LangfuseAuditPlugin(BasePlugin):
    """Adds banking-domain metadata and audit scores to Langfuse traces.

    The OTLP bridge handles all LLM/tool tracing automatically.
    This plugin supplements that with:
    - Transfer metadata (country, amount, status) on each trace
    - Audit scores (e.g., all required fields collected, validation passed)
    - Session-to-user mapping for compliance
    """

    def __init__(self, langfuse_client: Langfuse):
        super().__init__(name="langfuse_audit")
        self._langfuse = langfuse_client
        self._traces: dict[str, object] = {}  # invocation_id -> trace

    async def before_run_callback(self, *, invocation_context):
        """Create a Langfuse trace for each agent invocation."""
        trace = self._langfuse.trace(
            name="send-money-transfer",
            user_id=invocation_context.user_id,
            session_id=invocation_context.session.id,
            metadata={
                "app_name": invocation_context.app_name,
                "invocation_id": invocation_context.invocation_id,
            },
        )
        self._traces[invocation_context.invocation_id] = trace

    async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
        """Attach transfer state snapshot after each tool call."""
        trace = self._traces.get(tool_context.invocation_id)
        if trace and tool.name in ("update_transfer_field", "validate_transfer", "confirm_transfer"):
            draft = tool_context.state.get("transfer_draft", {})
            trace.update(
                metadata={
                    "transfer_country": draft.get("destination_country"),
                    "transfer_amount_currency": draft.get("amount_currency"),
                    "transfer_status": draft.get("status"),
                    "last_tool": tool.name,
                },
            )

    async def after_run_callback(self, *, invocation_context):
        """Score the trace for audit: were all fields collected?"""
        trace = self._traces.pop(invocation_context.invocation_id, None)
        if trace:
            draft = invocation_context.session.state.get("transfer_draft", {})
            required = ["destination_country", "amount_currency", "beneficiary_name", "delivery_method"]
            completeness = sum(1 for f in required if draft.get(f)) / len(required)
            trace.score(name="field_completeness", value=completeness)

    async def close(self):
        """Flush all pending Langfuse events on shutdown."""
        self._langfuse.flush()
```

### Wiring in Container

**`src/send_money/infrastructure/container.py`** (updated)
```python
class Container:
    def __init__(self):
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()

        from django.conf import settings

        # ... (repos, services, use cases as before) ...

        # Observability
        self._langfuse_client = None
        if settings.LANGFUSE_HOST:
            from langfuse import Langfuse
            from ..adapters.observability.otel_setup import setup_langfuse_otel

            # 1. OTLP bridge: ADK OTel → Langfuse (auto-traces everything)
            setup_langfuse_otel(
                langfuse_host=settings.LANGFUSE_HOST,
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
            )

            # 2. Langfuse SDK client for the audit plugin
            self._langfuse_client = Langfuse(
                host=settings.LANGFUSE_HOST,
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
            )

    def create_plugins(self) -> list:
        """Create ADK plugins. Returns empty list if Langfuse is not configured."""
        if not self._langfuse_client:
            return []
        from ..adapters.observability.langfuse_plugin import LangfuseAuditPlugin
        return [LangfuseAuditPlugin(self._langfuse_client)]
```

### Runner Setup with Plugins

**`main.py`** (updated)
```python
runner = Runner(
    app_name=settings.app_name,
    agent=container.create_agent(),
    session_service=container.create_session_service(),
    plugins=container.create_plugins(),  # NEW: Langfuse audit plugin
)
```

---

## Django Settings (updated for Langfuse)

**`config/settings.py`** additions:
```python
# Langfuse observability
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")

# OTel: control PII in spans (set "false" for production)
ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS = os.environ.get(
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "true"
)
```

---

## docker-compose.yml (updated with Langfuse stack)

```yaml
services:
  # ── Application Database ──────────────────────────────
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

  # ── Langfuse Observability Stack ──────────────────────
  langfuse-postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: langfuse
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse_dev
    volumes:
      - langfuse_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse -d langfuse"]
      interval: 5s
      timeout: 5s
      retries: 5

  langfuse-clickhouse:
    image: clickhouse/clickhouse-server:latest
    environment:
      CLICKHOUSE_DB: langfuse
      CLICKHOUSE_USER: langfuse
      CLICKHOUSE_PASSWORD: langfuse_dev
    volumes:
      - langfuse_chdata:/var/lib/clickhouse
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8123/ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  langfuse-redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  langfuse-minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: langfuse
      MINIO_ROOT_PASSWORD: langfuse_dev
    volumes:
      - langfuse_minio:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 5

  langfuse-server:
    image: langfuse/langfuse:latest
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse_dev@langfuse-postgres:5432/langfuse
      CLICKHOUSE_URL: http://langfuse-clickhouse:8123
      CLICKHOUSE_USER: langfuse
      CLICKHOUSE_PASSWORD: langfuse_dev
      REDIS_CONNECTION_STRING: redis://langfuse-redis:6379
      LANGFUSE_S3_EVENT_UPLOAD_BUCKET: langfuse
      LANGFUSE_S3_EVENT_UPLOAD_REGION: us-east-1
      LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID: langfuse
      LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY: langfuse_dev
      LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT: http://langfuse-minio:9000
      LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE: "true"
      NEXTAUTH_SECRET: local-dev-secret-change-in-prod
      SALT: local-dev-salt-change-in-prod
      NEXTAUTH_URL: http://localhost:3000
      # Auto-provision project with keys for local dev
      LANGFUSE_INIT_ORG_ID: local-dev
      LANGFUSE_INIT_ORG_NAME: "Local Dev"
      LANGFUSE_INIT_PROJECT_ID: send-money-agent
      LANGFUSE_INIT_PROJECT_NAME: "Send Money Agent"
      LANGFUSE_INIT_PROJECT_PUBLIC_KEY: pk-lf-local-dev
      LANGFUSE_INIT_PROJECT_SECRET_KEY: sk-lf-local-dev
      LANGFUSE_INIT_USER_EMAIL: dev@localhost
      LANGFUSE_INIT_USER_PASSWORD: password
    depends_on:
      langfuse-postgres:
        condition: service_healthy
      langfuse-clickhouse:
        condition: service_healthy
      langfuse-redis:
        condition: service_healthy
      langfuse-minio:
        condition: service_healthy

volumes:
  pgdata:
  langfuse_pgdata:
  langfuse_chdata:
  langfuse_minio:
```

---

## .env.example (updated)

```bash
# ── Application Database ──────────────────────────────
DB_NAME=send_money
DB_USER=send_money
DB_PASSWORD=send_money_dev
DB_HOST=localhost
DB_PORT=5432

# ── ADK Session Storage (SQLAlchemy + asyncpg internally) ──
ADK_DATABASE_URL=postgresql+asyncpg://send_money:send_money_dev@localhost:5432/send_money

# ── Google AI ─────────────────────────────────────────
GOOGLE_API_KEY=your-google-api-key

# ── Langfuse Observability ────────────────────────────
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-local-dev
LANGFUSE_SECRET_KEY=sk-lf-local-dev

# ── PII Control ──────────────────────────────────────
# Set to "false" in production to strip prompt/response content from traces
ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=true

# ── Django ────────────────────────────────────────────
DJANGO_SETTINGS_MODULE=config.settings
DJANGO_SECRET_KEY=dev-insecure-key
DJANGO_DEBUG=True
```

---

## What Langfuse Shows (per conversation)

After a transfer conversation, Langfuse at `http://localhost:3000` displays:

```
Trace: send-money-transfer
├── user_id: test_user
├── session_id: abc-123
├── metadata: { country: MX, amount_currency: USD, status: CONFIRMED }
├── score: field_completeness = 1.0
│
├── Span: invoke_agent [send_money_agent]
│   ├── Span: call_llm [gemini-2.5-flash]
│   │   ├── input_tokens: 342
│   │   ├── output_tokens: 87
│   │   └── content: "What country would you like to send money to?"
│   │
│   ├── Span: execute_tool [update_transfer_field]
│   │   ├── args: { field_name: "destination_country", field_value: "MX" }
│   │   └── response: { status: "updated" }
│   │
│   ├── Span: call_llm [gemini-2.5-flash]
│   │   └── content: "How much would you like to send?"
│   │
│   ├── Span: execute_tool [update_transfer_field] ...
│   ├── Span: execute_tool [validate_transfer] ...
│   ├── Span: call_llm → summary with fees ...
│   └── Span: execute_tool [confirm_transfer] ...
```

---

## Protobuf Schema

(Unchanged from v1/v2 — see plan_v2.md)

## Agent Design

(Unchanged from v1/v2 — see plan_v2.md)

## Django Models

(Unchanged from v2 — see plan_v2.md)

## Django Repository Implementations

(Unchanged from v2 — see plan_v2.md)

---

## Implementation Order

| # | Phase | What |
|---|-------|------|
| 1 | Foundation | Update `pyproject.toml` (add Django, psycopg, langfuse, OTel deps), `uv sync` |
| 2 | Foundation | Create dir structure, `docker-compose.yml` (PG18 + Langfuse stack), `config/settings.py`, `manage.py` |
| 3 | Domain | `enums.py`, `value_objects.py`, `entities.py`, `repositories.py`, `errors.py` |
| 4 | Protobuf | `.proto` files + `adapters/proto/converters.py` |
| 5 | Application | `ports.py`, 4 use case files |
| 6 | Django Models | `adapters/persistence/django_models.py`, `python manage.py makemigrations`, `migrate` |
| 7 | Persistence | `transfer_repository.py`, `corridor_repository.py` (Django ORM impls) |
| 8 | Observability | `otel_setup.py` (OTLP → Langfuse), `langfuse_plugin.py` (audit metadata/scores) |
| 9 | Infrastructure | `container.py` (wires repos + services + observability), `simulated_services.py` |
| 10 | Agent | `instructions.py`, `tools.py`, `agent_definition.py`, `agent.py`, `main.py` |
| 11 | Testing | Unit tests + integration tests + `test_langfuse_plugin.py` |

---

## Verification Checklist

- [ ] `uv sync` completes without errors
- [ ] `docker compose up -d` starts PG18 + Langfuse stack (5 containers total)
- [ ] Langfuse UI accessible at `http://localhost:3000` (login: `dev@localhost` / `password`)
- [ ] `python manage.py migrate` creates `transfers` + `corridors` tables
- [ ] `python manage.py seed_corridors` populates corridor data
- [ ] `uv run python main.py` — full conversation succeeds:
  - Open-ended "I want to send money" → agent asks missing fields
  - Mid-flow correction ("change country to Colombia") → handled correctly
  - `validate_transfer` → shows fees + FX rate
  - `confirm_transfer` → returns confirmation code
- [ ] Langfuse trace visible at `http://localhost:3000`:
  - Trace with user_id, session_id, metadata (country, amount, status)
  - Nested spans: invoke_agent → call_llm → execute_tool
  - Token usage on LLM spans
  - `field_completeness` score = 1.0
- [ ] `uv run pytest` — all tests pass
- [ ] `uv run mypy src/` — no type errors
- [ ] `uv run ruff check src/` — no lint errors

---

## Potential Pitfalls

| Risk | Mitigation |
|------|-----------|
| ADK's `DatabaseSessionService` requires SQLAlchemy+asyncpg internally | We don't fight this — pass it the `postgresql+asyncpg://` URL. Django uses `psycopg` for its own PG connection. Two drivers, one database. |
| Django ORM is sync-first; ADK tools are async | Use `sync_to_async` wrappers in repository implementations |
| `django.setup()` must be called before any ORM import | Container's `__init__` calls `django.setup()` first |
| `google.type.Money` serializes `units` as string in JSON | Handle in `dict_to_money_proto` with explicit `int()` cast |
| Langfuse OTLP endpoint may not be ready at startup | `BatchSpanProcessor` queues spans and retries; Langfuse `depends_on` health checks in docker-compose |
| Langfuse v3 needs ClickHouse + Redis + MinIO + PG | All included in docker-compose with health checks and volume persistence |
| `LANGFUSE_INIT_*` env vars auto-provision project only on first start | Documented in `.env.example`; keys are deterministic for local dev |
| OTel spans may contain PII (prompt/response content) | `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false` strips content from spans in production |
| `Event.is_final_response()` does not exist in ADK v1.28 | Filter by `event.author != "user"` and non-null text parts |

---

## Changes from v2

| Aspect | v2 | v3 |
|--------|----|----|
| Observability | None | Langfuse via OTLP + custom BasePlugin |
| New deps | — | `langfuse`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` |
| docker-compose | PG18 only (1 service) | PG18 + Langfuse stack (6 services) |
| New files | — | `otel_setup.py`, `langfuse_plugin.py`, `test_langfuse_plugin.py` |
| DI container | Repos + services | Repos + services + OTel setup + Langfuse plugin |
| Runner | No plugins | `plugins=container.create_plugins()` |
| Settings | DB + API key | + `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, PII control |
| Verification | CLI conversation + DB check | + Langfuse UI trace inspection |
