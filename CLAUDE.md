# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

This project uses Python 3.14 with a `.venv` virtual environment managed by `uv`.

```bash
uv sync          # install dependencies
source .venv/bin/activate
```

## Commands

```bash
uv run python main.py       # run the project
uv run pytest               # run tests
uv run pytest tests/test_foo.py::test_bar  # run a single test
```

## Workflow Orchestration

### 1. Plan Node Default
* Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
* If something goes sideways, **STOP** and re-plan immediately – don't keep pushing
* Use plan mode for verification steps, not just building
* Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
* Use subagents liberally to keep main context window clean
* Offload research, exploration, and parallel analysis to subagents
* For complex problems, throw more compute at it via subagents
* One task per subagent for focused execution

### 3. Self-Improvement Loop
* After ANY correction from the user: update `tasks/lessons.md` with the pattern
* Write rules for yourself that prevent the same mistake
* Ruthlessly iterate on these lessons until mistake rate drops
* Review lessons at session start for relevant project

### 4. Verification Before Done
* Never mark a task complete without proving it works
* Diff behavior between main and your changes when relevant
* Ask yourself: "Would a staff engineer approve this?"
* Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
* For non-trivial changes: pause and ask "is there a more elegant way?"
* If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
* Skip this for simple, obvious fixes – don't over-engineer
* Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
* When given a bug report: just fix it. Don't ask for hand-holding
* Point at logs, errors, failing tests – then resolve them
* Zero context switching required from the user
* Go fix failing CI tests without being told how

---

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

---

## Core Principles

* **Simplicity First**: Make every change as simple as possible. Impact minimal code.
* **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
* **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

## Architecture

- Follow **Clean Architecture** principles strictly: separate layers for entities, use cases, interface adapters, and frameworks/drivers.
- Dependencies must point inward — outer layers depend on inner layers, never the reverse.
- Each layer must communicate through **well-defined interfaces** (abstractions, not concretions).

## Dependency Injection

- **Dependency Injection is mandatory** for every module. No module should instantiate its own dependencies directly.
- All dependencies must be injected through constructors or dedicated DI containers.
- Prefer interface-based injection to keep modules decoupled and testable.

## Interfaces

- Every service, repository, and external integration must have a clearly defined interface.
- Implementations must be swappable without modifying consuming code.
- Keep interfaces minimal and focused (Interface Segregation Principle).

## AWS Services

- When working with AWS services (SDK, CDK, Lambda, S3, DynamoDB, SQS, etc.), **always use Context7 MCP to fetch up-to-date documentation** before writing or modifying code.
- Do not rely on cached or assumed knowledge for AWS APIs — resolve via Context7 first.

## Terraform

- All infrastructure must be defined as code using **Terraform**.
- When writing or modifying Terraform configurations, **always use Context7 MCP to fetch up-to-date Terraform documentation** (providers, resources, data sources).
- Follow Terraform best practices: use modules, variables, outputs, and remote state.

## General

- Write clean, testable, and maintainable code.
- Prefer composition over inheritance.
- Keep functions and methods small and focused on a single responsibility.

## venv usage
- always make use of project venv at .venv/ folder for python dependencies

## python style and formatter
- use ruff for formatting and linting
- use mypy to validate types and static typing
