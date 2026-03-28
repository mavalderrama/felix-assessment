# Send Money Agent — Architecture & How It Works

This document explains how the Send Money Agent is built, how it reasons, and how it interacts with a user from first message to final confirmation code. It is intended for developers onboarding to the codebase.

---

## Table of Contents

1. [What the agent does](#1-what-the-agent-does)
2. [Technology stack](#2-technology-stack)
3. [Architecture layers](#3-architecture-layers)
4. [Conversation lifecycle — step by step](#4-conversation-lifecycle--step-by-step)
5. [Session state and the `{transfer_draft}` mechanism](#5-session-state-and-the-transfer_draft-mechanism)
6. [The five tools](#6-the-five-tools)
7. [Domain model](#7-domain-model)
8. [Use cases (business logic)](#8-use-cases-business-logic)
9. [Dependency injection](#9-dependency-injection)
10. [Persistence](#10-persistence)
11. [Observability](#11-observability)
12. [Annotated example conversation](#12-annotated-example-conversation)
13. [Running the agent](#13-running-the-agent)
14. [Live showcase scenarios](#14-live-showcase-scenarios)

---

## 1. What the agent does

The Send Money Agent is a conversational AI that guides a user through an international money transfer over a text interface. The user does not fill in a form — they have a natural conversation. The agent:

- Collects the destination country, amount, currency, recipient name, and delivery method through dialogue
- Handles corrections mid-flow ("actually, make it 600 dollars")
- Calculates the fee and the amount the recipient will receive (using simulated FX rates)
- Asks the user to confirm the summary
- Atomically persists the transfer to PostgreSQL and returns a confirmation code

---

## 2. Technology stack

| Layer | Technology |
|---|---|
| LLM orchestration | [Google ADK](https://google.github.io/adk-docs/) v1.28+ |
| Language model | Gemini 2.5 Flash |
| Monetary values | `google.type.Money` (units + nanos integers, zero rounding error) |
| Runtime entities | Pydantic v2 |
| Application database | PostgreSQL 18 |
| ORM / migrations | Django 6 ORM + Django migrations |
| Session persistence | ADK `DatabaseSessionService` (SQLAlchemy + asyncpg) |
| Observability | OpenTelemetry → Langfuse (self-hosted) |
| Configuration | `python-dotenv` + Django settings |

---

## 3. Architecture layers

The codebase follows Clean Architecture. Dependencies always point **inward** — outer layers know about inner layers, never the reverse.

```
┌──────────────────────────────────────────────────────────────┐
│                     INFRASTRUCTURE                           │
│  Container (DI wiring), Django settings, simulated services  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                      ADAPTERS                          │  │
│  │  Agent (tools, instructions), Persistence (repos),     │  │
│  │  Observability (OTel, Langfuse plugin)                 │  │
│  │                                                        │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │               APPLICATION                        │  │  │
│  │  │  Use cases: collect · validate · confirm ·       │  │  │
│  │  │             get_corridors                        │  │  │
│  │  │  Ports (ABCs): ExchangeRateService, FeeService   │  │  │
│  │  │                                                  │  │  │
│  │  │  ┌────────────────────────────────────────────┐  │  │  │
│  │  │  │                 DOMAIN                     │  │  │  │
│  │  │  │  TransferDraft · Money · DeliveryMethod    │  │  │  │
│  │  │  │  TransferStatus · Repository ABCs · Errors │  │  │  │
│  │  │  └────────────────────────────────────────────┘  │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**Key files by layer:**

```
backend/
  config/settings.py                         ← Django settings (dotenv loaded here)
  send_money/
    domain/
      entities.py                            ← TransferDraft (Pydantic)
      value_objects.py                       ← Money (units/nanos, no floats)
      enums.py                               ← DeliveryMethod, TransferStatus, Country
      repositories.py                        ← Abstract repository interfaces
      errors.py                              ← Domain exceptions
    application/
      ports.py                               ← ExchangeRateService, FeeService ABCs
      use_cases/
        collect_transfer_details.py          ← Field-level validation + storage
        validate_transfer.py                 ← Corridor check + fee + FX calculation
        confirm_transfer.py                  ← Persistence + confirmation code
        get_corridors.py                     ← Read-only corridor queries
    adapters/
      agent/
        agent_definition.py                  ← Agent factory (model, config)
        instructions.py                      ← System prompt with {transfer_draft}
        tools.py                             ← 5 tool functions (closure factory)
      persistence/
        django_models.py                     ← Corridor, TransferRecord ORM models
        corridor_repository.py               ← DjangoCorridorRepository + InMemory
        transfer_repository.py               ← DjangoTransferRepository (atomic)
      observability/
        otel_setup.py                        ← OTel → Langfuse OTLP wiring
        langfuse_plugin.py                   ← ADK BasePlugin for audit metadata
      proto/
        converters.py                        ← Decimal ↔ Money ↔ dict conversions
    infrastructure/
      container.py                           ← DI Container (composition root)
      simulated_services.py                  ← Fake FX rates and fees
  main.py                                    ← Interactive CLI entry point
  agent.py                                   ← ADK CLI entry point (root_agent)
```

---

## 4. Conversation lifecycle — step by step

Here is what happens for every message the user sends:

```
User types a message
        │
        ▼
main.py: wrap in types.Content(role="user") → runner.run_async()
        │
        ▼
ADK Runner
  1. Load session from DatabaseSessionService
     (session.state contains the current transfer_draft dict)
  2. Resolve {transfer_draft} placeholder in the system prompt
     (ADK reads session.state["transfer_draft"] and injects it as text)
  3. Build the full prompt: system instruction + conversation history + new message
  4. Call Gemini 2.5 Flash with the prompt and tool schemas
        │
        ▼
Gemini 2.5 Flash decides what to do:
  Option A: Ask the user a question (text response, no tool call)
  Option B: Call one or more tools (function_call events)
        │
        ├── Option B: tool call(s)
        │       │
        │       ▼
        │   ADK dispatches to the matching tool function in tools.py
        │   The tool:
        │     • reads tool_context.state["transfer_draft"]
        │     • calls the appropriate use case
        │     • writes the updated draft back to tool_context.state
        │     • returns a result dict to the LLM
        │       │
        │       ▼
        │   Gemini receives tool result(s) and decides again:
        │     • call more tools, or
        │     • generate a text response
        │
        ▼
ADK streams events back through runner.run_async()
main.py filters for text-only events (skips function_call / function_response)
and prints the agent's reply to the user
        │
        ▼
ADK persists the updated session state (including the new transfer_draft)
to DatabaseSessionService → PostgreSQL
```

The loop repeats for every user message until the transfer is confirmed or the user exits.

---

## 5. Session state and the `{transfer_draft}` mechanism

Session state is the memory that persists across conversation turns. ADK stores it in its own PostgreSQL table (managed by `DatabaseSessionService`).

The transfer draft lives at `session.state["transfer_draft"]` as a flat JSON dict:

```json
{
  "transfer_draft": {
    "destination_country": "MX",
    "amount_units": 500,
    "amount_nanos": 0,
    "amount_currency": "USD",
    "beneficiary_name": "Maria Garcia",
    "delivery_method": "BANK_DEPOSIT",
    "status": "COLLECTING",
    "fee_units": null,
    "fee_nanos": null,
    "receive_amount_units": null,
    "receive_amount_nanos": null
  }
}
```

**How `{transfer_draft}` works in the system prompt:**

The system prompt (`instructions.py`) contains the literal string `{transfer_draft}`. ADK resolves this at runtime: before calling the LLM, it looks up `session.state["transfer_draft"]` and substitutes it into the prompt. This means the LLM always sees the *current* state of the draft — it never needs to remember what was said two turns ago. This is what allows the agent to ask only for fields that are still `null` and to detect when all required fields are set.

```python
# From instructions.py
SEND_MONEY_INSTRUCTION = """
You are a Send Money Agent ...

Current transfer state:
{transfer_draft}          ← ADK replaces this with the actual dict each turn

━━━ REQUIRED FIELDS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
...
"""
```

**Tools write to session state:**

Every tool that modifies the draft writes it back to `tool_context.state`:

```python
# From tools.py — after update_transfer_field() runs
tool_context.state["transfer_draft"] = updated.to_state_dict()
```

ADK automatically persists this to its database at the end of the invocation, so the next turn starts with the correct draft.

---

## 6. The five tools

Tools are the only way the agent can take action. They are plain async Python functions injected into the `Agent` via the `tools=` parameter. The LLM decides when and how to call them based on its docstrings.

All five are created by `create_tools(container)` in `adapters/agent/tools.py` — a closure factory that captures the use-case instances at startup so there is no global state.

### Tool 1: `update_transfer_field`

```
update_transfer_field(field_name: str, field_value: str, tool_context) -> dict
```

**When called:** Any time the user provides a value for one of the five required fields, or wants to change an existing value.

**What it does:**
1. Reads the current draft from `tool_context.state["transfer_draft"]`
2. Calls `CollectTransferDetailsUseCase.execute(draft_dict, field_name, field_value)`
3. The use case validates the value (e.g., country must be supported, amount must be positive)
4. Writes the updated draft back to session state
5. Returns `{"status": "updated", "field": ..., "missing_fields": [...]}` so the LLM knows what to collect next

**On validation error:** Returns `{"status": "error", "message": ...}` — the LLM relays this to the user.

**Note:** If the user says "500 dollars", the LLM calls this tool *twice* — once for `amount` and once for `currency`.

### Tool 2: `validate_transfer`

```
validate_transfer(tool_context) -> dict
```

**When called:** Automatically after all required fields are set (the LLM detects this from `missing_fields` being empty).

**What it does:**
1. Calls `ValidateTransferUseCase.execute(draft_dict)`
2. The use case: checks corridor is supported, resolves destination currency, calls the fee service, calls the FX rate service, calculates receive amount
3. Writes the validated draft (status=`VALIDATED`) back to session state
4. Returns a summary dict:

```json
{
  "status": "validated",
  "send_amount": "500.00 USD",
  "fee": "2.99 USD",
  "destination_currency": "MXN",
  "receive_amount": "8725.00 MXN",
  "destination_country": "MX",
  "beneficiary_name": "Maria Garcia",
  "delivery_method": "BANK_DEPOSIT"
}
```

### Tool 3: `confirm_transfer`

```
confirm_transfer(tool_context) -> dict
```

**When called:** Only after the user explicitly says "yes" or "confirm" in response to the summary.

**What it does:**
1. Extracts `session_id` and `user_id` from `tool_context`
2. Calls `ConfirmTransferUseCase.execute(draft_dict, session_id, user_id)`
3. The use case generates a UUID, idempotency key, and confirmation code, then atomically persists the transfer to PostgreSQL
4. Returns `{"status": "confirmed", "confirmation_code": "SM-A3F2B1", "transfer_id": "..."}`

### Tool 4: `get_supported_countries`

```
get_supported_countries(tool_context) -> dict
```

**When called:** If the user asks "which countries do you support?" before providing a destination.

**Returns:** `{"supported_countries": ["CO", "GB", "GT", "IN", "MX", "PH"]}`

### Tool 5: `get_delivery_methods`

```
get_delivery_methods(country_code: str, tool_context) -> dict
```

**When called:** If the user asks "what options are available for Mexico?" or when the agent needs to present delivery choices for a country.

**Returns:** `{"country": "MX", "delivery_methods": ["BANK_DEPOSIT", "CASH_PICKUP", "MOBILE_WALLET"]}`

---

## 7. Domain model

### `TransferDraft` — `domain/entities.py`

The central entity, implemented as a Pydantic `BaseModel`. It represents a transfer being assembled across multiple conversation turns. All fields are optional until collected:

| Field | Type | Description |
|---|---|---|
| `id` | `str \| None` | UUID, assigned at confirmation |
| `destination_country` | `str \| None` | ISO 3166-1 alpha-2 (e.g. `"MX"`) |
| `amount_units` | `int \| None` | Whole currency units (e.g. `500`) |
| `amount_nanos` | `int \| None` | Fractional part in nanoseconds (e.g. `990_000_000` = 0.99) |
| `amount_currency` | `str \| None` | ISO 4217 source currency (e.g. `"USD"`) |
| `beneficiary_name` | `str \| None` | Recipient's full name |
| `delivery_method` | `DeliveryMethod \| None` | `BANK_DEPOSIT`, `MOBILE_WALLET`, or `CASH_PICKUP` |
| `status` | `TransferStatus` | `COLLECTING` → `VALIDATED` → `CONFIRMED` |
| `fee_units` / `fee_nanos` | `int \| None` | Calculated fee (same currency as amount) |
| `receive_amount_units` / `receive_amount_nanos` | `int \| None` | What the recipient gets |
| `confirmation_code` | `str \| None` | e.g. `"SM-A3F2B1"`, assigned at confirmation |

Key properties:
- `missing_fields` — returns a list of required field names that are still `None`
- `is_complete` — `True` when all 5 required fields are set
- `to_state_dict()` / `from_state_dict()` — serialize to/from ADK session state

### `Money` — `domain/value_objects.py`

An immutable `dataclass` that stores monetary values as `(units: int, nanos: int, currency_code: str)`, mirroring the `google.type.Money` protobuf. This is the key design decision that prevents rounding errors.

**Why integers instead of floats?**

```python
# Float arithmetic — WRONG for banking:
0.1 + 0.2 == 0.3  # False in IEEE 754

# Money with integers — always exact:
m1 = Money.from_decimal(Decimal("0.1"), "USD")   # units=0, nanos=100_000_000
m2 = Money.from_decimal(Decimal("0.2"), "USD")   # units=0, nanos=200_000_000
m1.to_decimal() + m2.to_decimal() == Decimal("0.3")  # True, always
```

A value of `42.99 USD` is stored as:
- `units = 42` (the whole number part)
- `nanos = 990_000_000` (0.99 × 1,000,000,000)
- `currency_code = "USD"`

**Conversion:**
```python
# Decimal → Money (via integer arithmetic only, never float)
Money.from_decimal(Decimal("42.99"), "USD")

# Money → Decimal (exact reconstruction)
money.to_decimal()  # → Decimal("42.99")

# Money → protobuf message
money.to_proto()  # → google.type.Money

# Money → session state dict
money.to_dict()   # → {"units": 42, "nanos": 990_000_000, "currency_code": "USD"}
```

### Status transitions

```
COLLECTING  →  VALIDATED  →  CONFIRMED
    ↑               │
    └───────────────┘  (user corrects a field → back to COLLECTING)
```

When the user corrects any field after validation, `update_transfer_field` resets calculated fields (`fee`, `receive_amount`) and the status reverts to `COLLECTING`, forcing a fresh `validate_transfer` call.

---

## 8. Use cases (business logic)

Use cases live in `application/use_cases/` and are the only place where business rules are enforced. They depend only on domain entities and repository/service abstractions — never on Django, ADK, or any framework.

### `CollectTransferDetailsUseCase`

**File:** `application/use_cases/collect_transfer_details.py`

Validates and stores one field at a time. Uses a `match` statement on `field_name`:

- **`destination_country`**: Uppercases the code, checks it against `corridor_repository.get_supported_countries()`. If the country changes, resets `delivery_method` and all calculated fields to ensure consistency.
- **`amount`**: Parses the string to `Decimal` (accepts commas, e.g. `"1,000"`), rejects non-positive values, converts to `Money(units, nanos)`.
- **`currency`**: Validates as exactly 3 alphabetic characters (ISO 4217). Sets both `amount_currency` and `source_currency`.
- **`beneficiary_name`**: Requires at least 2 characters after stripping whitespace.
- **`delivery_method`**: Validates against the `DeliveryMethod` enum. If a country is already set, validates the method is available for that country via `corridor_repository.get_delivery_methods()`.

Raises `InvalidFieldError` on any validation failure.

### `ValidateTransferUseCase`

**File:** `application/use_cases/validate_transfer.py`

Runs after all fields are collected:

1. Checks `draft.is_complete` — raises `InvalidFieldError` if any required field is missing
2. Checks `corridor_repository.is_supported(country, method)` — raises `UnsupportedCorridorError` if the combination is not in the corridors table
3. Resolves `destination_currency` from the corridor record
4. Calls `fee_service.calculate_fee(amount_units, amount_nanos, country, method)` → `(fee_units, fee_nanos)`
5. Calls `exchange_rate_service.get_rate(source_currency, dest_currency)` → `Decimal` rate
6. Multiplies the send amount by the rate using `Decimal` arithmetic → converts to `Money` for the receive amount
7. Sets `draft.status = VALIDATED`

### `ConfirmTransferUseCase`

**File:** `application/use_cases/confirm_transfer.py`

Requires `draft.status == VALIDATED` — raises `InvalidFieldError` otherwise:

1. Generates a UUID v4 for `draft.id`
2. Generates an idempotency key: `f"{session_id}:{country}:{amount_units}:{beneficiary_name}"`
3. Generates a human-readable confirmation code: `f"SM-{uuid4().hex[:6].upper()}"` (e.g. `SM-A3F2B1`)
4. Calls `transfer_repository.save(draft)` which atomically persists the record (see Persistence section)

### `GetCorridorsUseCase`

**File:** `application/use_cases/get_corridors.py`

A thin read-only facade over `CorridorRepository`:
- `get_supported_countries()` — returns sorted list of active country codes
- `get_delivery_methods(country_code)` — returns available delivery methods for a country

---

## 9. Dependency injection

All dependencies are wired in `infrastructure/container.py`. The `Container` class is the *composition root* — the single place where concrete implementations are selected and connected.

```python
class Container:
    def __init__(self):
        _bootstrap_django()                          # django.setup() if needed

        # Repositories (concrete implementations)
        self.corridor_repository = DjangoCorridorRepository()
        self.transfer_repository = DjangoTransferRepository()

        # Simulated external services
        self.exchange_rate_service = SimulatedExchangeRateService()
        self.fee_service = SimulatedFeeService()

        # Use cases — all dependencies injected via constructor
        self.collect_uc  = CollectTransferDetailsUseCase(self.corridor_repository)
        self.validate_uc = ValidateTransferUseCase(
            self.corridor_repository, self.exchange_rate_service, self.fee_service
        )
        self.confirm_uc   = ConfirmTransferUseCase(self.transfer_repository)
        self.corridors_uc = GetCorridorsUseCase(self.corridor_repository)
```

**Closure factory for tools:**

ADK tools must be plain Python callables. The `create_tools(container)` factory returns closures that capture the use-case instances — no global variables, fully testable:

```python
def create_tools(container):
    collect_uc  = container.collect_uc   # captured at construction time
    validate_uc = container.validate_uc

    async def update_transfer_field(field_name, field_value, tool_context):
        # collect_uc is available here via closure
        updated = await collect_uc.execute(...)
        ...

    return [update_transfer_field, validate_transfer, ...]
```

**Swapping implementations** (e.g. replacing `SimulatedExchangeRateService` with a real API client) only requires changing one line in `container.py` — no other file needs to change.

---

## 10. Persistence

The system uses two separate database strategies that share the same PostgreSQL 18 instance:

### ADK session database (SQLAlchemy + asyncpg)

ADK's `DatabaseSessionService` manages its own schema for session/conversation history. It is configured via `ADK_DATABASE_URL`:

```python
# container.py
def create_session_service(self):
    return DatabaseSessionService(settings.ADK_DATABASE_URL)
```

This is where `session.state["transfer_draft"]` is persisted between turns.

### Domain database (Django ORM)

Django manages the `corridors` and `transfers` tables via its own migrations (in `backend/migrations/`). Two Django models are defined in `adapters/persistence/django_models.py`:

- **`Corridor`**: `country_code`, `delivery_method`, `currency_code`, `is_active`
- **`TransferRecord`**: All transfer fields with `DecimalField(max_digits=19, decimal_places=4)` mapping to PostgreSQL `NUMERIC(19,4)`. Has a `CheckConstraint` ensuring `amount > 0`.

### Idempotency and atomic writes

`DjangoTransferRepository.save()` prevents double-submission using `SELECT FOR UPDATE` inside a transaction:

```python
async def save(self, draft: TransferDraft) -> TransferDraft:
    @sync_to_async
    def _save():
        with transaction.atomic():
            existing = (
                TransferRecord.objects
                .select_for_update()
                .filter(idempotency_key=draft.idempotency_key)
                .first()
            )
            if existing:
                return _to_entity(existing)   # idempotent: return existing record
            record = TransferRecord(...)
            record.save()
            return _to_entity(record)
    return await _save()
```

The idempotency key is `f"{session_id}:{country}:{amount_units}:{beneficiary_name}"`. If the user hits confirm twice (e.g. network retry), the second call returns the same confirmation code instead of creating a duplicate transfer.

All ORM calls are wrapped in `sync_to_async` because ADK's tool execution is async, but Django's ORM is synchronous.

---

## 11. Observability

The agent emits telemetry on two levels.

### OpenTelemetry traces (auto-instrumented)

`adapters/observability/otel_setup.py` wires ADK's built-in OTel pipeline to export traces to Langfuse's OTLP endpoint:

```
ADK (auto-instruments all spans)
        │  BatchSpanProcessor
        ▼
OTLPSpanExporter
        │  OTLP/HTTP + Basic Auth
        ▼
Langfuse: http://localhost:3010/api/public/otel/v1/traces
```

ADK automatically creates spans for:
- Each agent invocation
- Each LLM call (prompt, model, latency, token counts)
- Each tool call (function name, arguments, result)

No custom spans need to be written.

### Langfuse audit plugin (banking metadata)

`adapters/observability/langfuse_plugin.py` implements `BasePlugin` and supplements the OTel traces with domain-specific metadata:

| Hook | What it does |
|---|---|
| `before_run_callback` | Creates a Langfuse trace named `"send-money-transfer"` with `user_id`, `session_id`, `invocation_id` |
| `after_tool_callback` | After `update_transfer_field`, `validate_transfer`, or `confirm_transfer`: attaches current transfer country, currency, status, and last tool name to the trace |
| `after_run_callback` | Calculates `field_completeness` score (0.0–1.0) based on how many required fields are filled. Logs it as a Langfuse score |
| `close` | Flushes the Langfuse client to avoid losing buffered events |

The plugin is only registered when `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are configured. If they are absent (e.g. in tests), the plugins list is empty and no tracing overhead is added.

---

## 12. Annotated example conversation

Below is a full conversation trace showing the user's messages, the LLM's tool calls, session state changes, and what the user sees.

---

**Turn 1**

```
User: "I want to send money to my sister in Mexico"

LLM sees in system prompt:
  transfer_draft = {}   (empty — nothing collected yet)

LLM decides:
  → call update_transfer_field("destination_country", "MX")

Tool execution:
  CollectTransferDetailsUseCase validates "MX" (it's in supported countries)
  Session state after:
    {"destination_country": "MX", "status": "COLLECTING", ...rest null}

LLM receives tool result:
  {"status": "updated", "field": "destination_country", "missing_fields":
   ["amount_units", "amount_currency", "beneficiary_name", "delivery_method"]}

LLM generates text:
  "Got it — Mexico. How much would you like to send, and in which currency?"

User sees: "Got it — Mexico. How much would you like to send, and in which currency?"
```

---

**Turn 2**

```
User: "500 US dollars"

LLM sees in system prompt:
  transfer_draft = {"destination_country": "MX", ...rest null}

LLM decides:
  → call update_transfer_field("amount", "500")
  → call update_transfer_field("currency", "USD")   (two calls for one message)

Tool execution (call 1 — amount):
  Sets amount_units=500, amount_nanos=0
  Session state: {"destination_country": "MX", "amount_units": 500, "amount_nanos": 0, ...}

Tool execution (call 2 — currency):
  Sets amount_currency="USD", source_currency="USD"
  Session state: {..."amount_currency": "USD", "source_currency": "USD", ...}

LLM receives both tool results:
  missing_fields: ["amount_currency"... wait, currency is now set too]
  missing_fields: ["beneficiary_name", "delivery_method"]

LLM generates text:
  "Who is the recipient, and would you prefer bank deposit, mobile wallet, or cash pickup?"

User sees: "Who is the recipient, and would you prefer bank deposit, mobile wallet, or cash pickup?"
```

---

**Turn 3**

```
User: "Maria Garcia, bank deposit please"

LLM calls:
  → update_transfer_field("beneficiary_name", "Maria Garcia")
  → update_transfer_field("delivery_method", "BANK_DEPOSIT")

After both tools: missing_fields = []   ← all required fields are set!

LLM automatically calls:
  → validate_transfer()

ValidateTransferUseCase runs:
  1. Checks MX/BANK_DEPOSIT is in corridors table ✓
  2. Destination currency = "MXN"
  3. Fee = 2.99 USD (simulated)
  4. Exchange rate USD→MXN = 17.45 (simulated)
  5. Receive amount = (500 - 0) × 17.45 = 8,725.00 MXN
     (fee is informational, not deducted from send amount in simulation)
  6. status = VALIDATED

Session state now includes:
  {
    "status": "VALIDATED",
    "destination_currency": "MXN",
    "fee_units": 2, "fee_nanos": 990_000_000,
    "receive_amount_units": 8725, "receive_amount_nanos": 0
  }

validate_transfer returns:
  {
    "send_amount": "500.00 USD",
    "fee": "2.99 USD",
    "receive_amount": "8725.00 MXN",
    "beneficiary_name": "Maria Garcia",
    "delivery_method": "BANK_DEPOSIT"
  }

LLM generates text:
  "Here's your transfer summary:
   • Send: 500.00 USD
   • Fee: 2.99 USD
   • Maria Garcia receives: 8,725.00 MXN via bank deposit in Mexico

   Shall I confirm this transfer?"
```

---

**Turn 4 — correction**

```
User: "Actually, make it 600 dollars"

LLM calls:
  → update_transfer_field("amount", "600")

CollectTransferDetailsUseCase:
  Sets amount_units=600, resets fee_units/fee_nanos/receive_amount to null
  status stays COLLECTING (collected field changed → re-validation needed)

LLM notices missing_fields is still [] (all required fields still set)
LLM automatically calls:
  → validate_transfer()   ← fresh calculation with new amount

New receive amount: 600 × 17.45 = 10,470.00 MXN

LLM generates text:
  "Updated! Here's the revised summary:
   • Send: 600.00 USD
   • Fee: 2.99 USD
   • Maria Garcia receives: 10,470.00 MXN via bank deposit in Mexico

   Would you like to confirm?"
```

---

**Turn 5 — confirmation**

```
User: "Yes, confirm it"

LLM calls:
  → confirm_transfer()

ConfirmTransferUseCase:
  1. draft.status == VALIDATED ✓
  2. Generates id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
  3. idempotency_key = "session-abc:MX:600:Maria Garcia"
  4. confirmation_code = "SM-D4E2F1"
  5. Calls DjangoTransferRepository.save() within SELECT FOR UPDATE transaction
  6. status = CONFIRMED

confirm_transfer returns:
  {"status": "confirmed", "confirmation_code": "SM-D4E2F1", "transfer_id": "f47ac10b-..."}

LLM generates text:
  "Your transfer is confirmed! Reference code: SM-D4E2F1
   Maria Garcia will receive 10,470.00 MXN in Mexico via bank deposit."

User sees: "Your transfer is confirmed! Reference code: SM-D4E2F1 ..."
```

---

## 13. Running the agent

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Docker + Docker Compose | 24+ | For the infrastructure stack |
| Python | 3.14 | Matches `.python-version` |
| [uv](https://docs.astral.sh/uv/) | latest | Package manager (`pip install uv`) |
| Google API key | — | Gemini access via [Google AI Studio](https://aistudio.google.com/apikey) |

---

### Step 1 — Start the infrastructure stack

```bash
docker compose up -d
```

This starts five services: **postgres** (app + Langfuse DB), **langfuse-clickhouse**, **langfuse-redis**, **langfuse-minio**, and **langfuse-server**.

Wait until all services are healthy:

```bash
docker compose ps
# All services should show "healthy" or "running"
```

ClickHouse takes ~30 s to initialise. If `langfuse-server` exits immediately, wait a moment and run `docker compose up -d` again.

---

### Step 2 — Install Python dependencies

```bash
uv sync
source .venv/bin/activate
```

---

### Step 3 — Configure environment

Copy the example file and fill in your Google API key:

```bash
cp .env.example .env
```

Edit `.env` and set:

```bash
GOOGLE_API_KEY=your-key-here   # Required — agent will not start without this
```

All other values are pre-configured for the local Docker stack:

| Variable | Value | Purpose |
|---|---|---|
| `DB_PORT` | `5434` | Host-mapped PostgreSQL port |
| `ADK_DATABASE_URL` | `postgresql+asyncpg://...@localhost:5434/send_money` | ADK session persistence |
| `LANGFUSE_HOST` | `http://localhost:3010` | Observability UI |
| `LANGFUSE_PUBLIC_KEY` | `pk-lf-local-dev` | Matches docker-compose init |
| `LANGFUSE_SECRET_KEY` | `sk-lf-local-dev` | Matches docker-compose init |

---

### Step 4 — Run database migrations

```bash
python backend/manage.py migrate
```

This creates the `corridors` and `transfers` tables in PostgreSQL.

---

### Step 5 — Seed reference data

```bash
# Seed corridor configuration (11 records across 6 countries)
python backend/manage.py seed_corridors

# Seed synthetic historical transfers (10 records for demo purposes)
python backend/manage.py seed_transfers
```

To reset transfers and re-seed from scratch:

```bash
python backend/manage.py seed_transfers --clear
```

---

### Step 6 — Start the agent

**Option A — Interactive CLI** (recommended for demos):

```bash
python backend/main.py
```

The agent starts a REPL. Type a message and press Enter. Type `exit` or `quit` to stop.

**Option B — ADK Web UI** (visual tool-call inspector):

```bash
adk web backend/send_money/agent.py
```

Opens a browser UI at `http://localhost:8000` with a chat interface and a panel showing every tool call and its arguments in real time.

---

### Step 7 — Run the test suite

```bash
pytest backend/tests/unit/ -q
```

Expected output: 63 tests, all passing. No database or API key required for unit tests.

---

### Step 8 — View traces in Langfuse

Navigate to **[http://localhost:3010](http://localhost:3010)** and log in:

- **Email:** `dev@localhost.local`
- **Password:** `password`

Select the **Send Money Agent** project. After each agent session a trace appears with nested spans for every LLM call and tool invocation, plus a `field_completeness` quality score (0.0–1.0).

---

### Teardown

Stop the stack (keep data volumes):

```bash
docker compose down
```

Stop and wipe all data (clean slate):

```bash
docker compose down -v
```

After `-v` you must re-run Steps 4–5 before starting the agent again.

---

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `langfuse-server` exits immediately | ClickHouse not ready | Wait 30 s, run `docker compose up -d` again |
| `Error: GOOGLE_API_KEY not set` | Missing env var | Set `GOOGLE_API_KEY` in `.env` |
| `connection refused :5434` | Postgres not started | Run `docker compose up -d` first |
| `P1001: Can't reach database at postgres:5434` | Wrong port in DATABASE_URL | Container-internal port is 5432; check `docker-compose.yml` |
| `ClickHouse migrations failed` | Volume has stale data | Run `docker compose down -v && docker compose up -d` |
| Tests fail with `ImproperlyConfigured` | Django settings not found | Ensure `DJANGO_SETTINGS_MODULE=config.settings` is in `.env` |

---

## 14. Live showcase scenarios

These scenarios are designed for live demos. Each one exercises a different aspect of the agent's behaviour. Run `python backend/main.py` and use the suggested messages verbatim or paraphrase naturally.

---

### Scenario 1 — Happy path (Mexico, bank deposit)

**Goal:** Show the complete, uninterrupted flow from first message to confirmation code.

**Story:** A user sends $300 to their mother in Mexico via bank deposit.

```
You:    I'd like to send money to Mexico
Agent:  [calls update_transfer_field("destination_country", "MX")]
        "Got it — Mexico. How much would you like to send?"

You:    300 dollars
Agent:  [calls update_transfer_field("amount", "300"),
              update_transfer_field("currency", "USD")]
        "And who is the recipient?"

You:    Rosa Ramirez, bank deposit please
Agent:  [calls update_transfer_field("beneficiary_name", "Rosa Ramirez"),
              update_transfer_field("delivery_method", "BANK_DEPOSIT"),
              validate_transfer()]
        "Here's your summary:
         • Send: 300.00 USD  •  Fee: 2.99 USD
         • Rosa Ramirez receives: 5,235.00 MXN via bank deposit in Mexico
         Shall I confirm?"

You:    Yes, confirm
Agent:  [calls confirm_transfer()]
        "Confirmed! Reference: SM-XXXXXX"
```

**Points to highlight:**
- The agent infers country code `MX` from "Mexico" without being told the code
- Two tools are called in one turn when the user says "300 dollars" (amount + currency)
- `validate_transfer` is called automatically once `missing_fields` is empty
- The confirmation code is persisted atomically — running confirm twice returns the same code

---

### Scenario 2 — Mid-flow correction (amount change after validation)

**Goal:** Show that the agent gracefully handles corrections and re-validates.

**Story:** The user changes the amount after seeing the summary.

```
You:    Send 200 USD to Carlos Hernandez in Colombia, bank deposit
Agent:  [calls update_transfer_field x4, then validate_transfer()]
        "Summary: 200.00 USD  •  Fee: 3.49 USD
         Carlos Hernandez receives: 824,100.00 COP via bank deposit
         Confirm?"

You:    Actually, make it 500 dollars
Agent:  [calls update_transfer_field("amount", "500"),
              validate_transfer()]
        "Updated! New summary:
         • Send: 500.00 USD  •  Fee: 3.49 USD
         • Carlos Hernandez receives: 2,060,250.00 COP
         Shall I confirm?"

You:    Yes
Agent:  [calls confirm_transfer()]
        "Confirmed! Reference: SM-XXXXXX"
```

**Points to highlight:**
- Changing the amount resets `fee` and `receive_amount` to null in session state
- The agent automatically calls `validate_transfer` again because `missing_fields` is still empty
- Status transitions: VALIDATED → COLLECTING (on correction) → VALIDATED → CONFIRMED

---

### Scenario 3 — Country change cascades to delivery method reset

**Goal:** Show how the agent handles a field that invalidates a downstream field.

**Story:** User starts with Mexico + mobile wallet, then switches to India (which only supports bank deposit).

```
You:    I want to send 400 dollars to Ana Torres in Mexico, mobile wallet
Agent:  [calls update_transfer_field x4, validate_transfer()]
        "Summary: 400 USD → Ana Torres in Mexico, MOBILE_WALLET
         Fee: 1.99 USD. Receives 6,980.00 MXN. Confirm?"

You:    Actually, send it to India instead
Agent:  [calls update_transfer_field("destination_country", "IN")]
        "Changed to India. Note: mobile wallet isn't available there —
         only bank deposit is supported. Which would you like?"

You:    Bank deposit
Agent:  [calls update_transfer_field("delivery_method", "BANK_DEPOSIT"),
              validate_transfer()]
        "Updated! Ana Torres receives 33,248.00 INR via bank deposit. Confirm?"

You:    Confirm
Agent:  [calls confirm_transfer()]
```

**Points to highlight:**
- Changing `destination_country` resets `delivery_method` to null (use-case enforces this)
- The agent recognises the previous delivery method is invalid for India and prompts again
- India only supports `BANK_DEPOSIT` — the agent surfaces this from `get_delivery_methods`

---

### Scenario 4 — Exploring options before starting

**Goal:** Show the informational tools (`get_supported_countries`, `get_delivery_methods`).

**Story:** A first-time user explores what's available before committing.

```
You:    What countries can I send money to?
Agent:  [calls get_supported_countries()]
        "We support: Colombia (CO), Great Britain (GB), Guatemala (GT),
         India (IN), Mexico (MX), and Philippines (PH)."

You:    What delivery options does Philippines have?
Agent:  [calls get_delivery_methods("PH")]
        "For Philippines: bank deposit or mobile wallet."

You:    Great, send 150 USD to Maria Santos in the Philippines, mobile wallet
Agent:  [calls update_transfer_field x4, validate_transfer()]
        "Maria Santos receives 8,445.00 PHP via mobile wallet. Fee: 1.49 USD. Confirm?"

You:    Yes
Agent:  [calls confirm_transfer()]
```

**Points to highlight:**
- The agent answers discovery questions without pushing the user to start a transfer
- `get_delivery_methods` is called with the country code inferred from "Philippines"
- PHP mobile wallet has the lowest fee in the system ($1.49)

---

### Scenario 5 — Invalid input recovery

**Goal:** Show validation error handling — the agent explains the problem and asks again without losing state.

**Story:** A user provides several invalid inputs before getting through.

```
You:    Send money to Venezuela
Agent:  [calls update_transfer_field("destination_country", "VE")]
        "Sorry, Venezuela isn't supported yet. Supported countries are:
         CO, GB, GT, IN, MX, PH. Where would you like to send?"

You:    Guatemala then
Agent:  [calls update_transfer_field("destination_country", "GT")]
        "Got it — Guatemala. How much?"

You:    -50 dollars
Agent:  [calls update_transfer_field("amount", "-50")]
        "The amount must be a positive number. Please try again."

You:    50 dollars
Agent:  [calls update_transfer_field("amount", "50"),
              update_transfer_field("currency", "USD")]
        "And the recipient's name?"

You:    J
Agent:  [calls update_transfer_field("beneficiary_name", "J")]
        "The recipient's name must be at least 2 characters. Please provide
         the full name."

You:    Juan Morales, cash pickup
Agent:  [calls update_transfer_field("beneficiary_name", "Juan Morales"),
              update_transfer_field("delivery_method", "CASH_PICKUP"),
              validate_transfer()]
        "Juan Morales receives 386.00 GTQ via cash pickup in Guatemala.
         Fee: 4.99 USD. Confirm?"

You:    Yes
Agent:  [calls confirm_transfer()]
```

**Points to highlight:**
- Each `InvalidFieldError` from the use case is surfaced as a clear message — no crash
- Session state is preserved across failed attempts — country stays set after amount fails
- The agent batches the valid fields in the final turn and moves forward efficiently
