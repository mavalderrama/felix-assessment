"""Dependency Injection container — wires all layers together.

django.setup() is called here before any ORM import so the container is safe
to instantiate from any entry point (main.py, agent.py, tests).
"""
from __future__ import annotations

import os

from send_money.adapters.persistence.audit_log_repository import DjangoAuditLogRepository
from send_money.adapters.persistence.corridor_repository import DjangoCorridorRepository
from send_money.adapters.persistence.exchange_rate_repository import DjangoExchangeRateRepository
from send_money.adapters.persistence.transfer_repository import DjangoTransferRepository
from send_money.application.use_cases.collect_transfer_details import CollectTransferDetailsUseCase
from send_money.application.use_cases.confirm_transfer import ConfirmTransferUseCase
from send_money.application.use_cases.get_corridors import GetCorridorsUseCase
from send_money.application.use_cases.validate_transfer import ValidateTransferUseCase
from send_money.infrastructure.simulated_services import (
    SimulatedExchangeRateService,
    SimulatedFeeService,
)


def _bootstrap_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    import django.conf

    if not django.conf.settings.configured:
        django.setup()


class Container:
    def __init__(self) -> None:
        _bootstrap_django()

        # Repositories
        self.corridor_repository = DjangoCorridorRepository()
        self.transfer_repository = DjangoTransferRepository()
        self.exchange_rate_repository = DjangoExchangeRateRepository()
        self.audit_log_repository = DjangoAuditLogRepository()

        # Simulated external services
        self.exchange_rate_service = SimulatedExchangeRateService(self.exchange_rate_repository)
        self.fee_service = SimulatedFeeService()

        # Use cases — constructor-injected
        self.collect_uc = CollectTransferDetailsUseCase(self.corridor_repository)
        self.validate_uc = ValidateTransferUseCase(
            self.corridor_repository,
            self.exchange_rate_service,
            self.fee_service,
        )
        self.confirm_uc = ConfirmTransferUseCase(
            self.transfer_repository,
            self.audit_log_repository,
        )
        self.corridors_uc = GetCorridorsUseCase(self.corridor_repository)

        # Observability (optional — skipped if keys are not configured)
        self._langfuse_client = self._build_langfuse_client()

    # ── Factory methods ──────────────────────────────────────

    def create_session_service(self):
        from django.conf import settings
        from google.adk.sessions import DatabaseSessionService

        return DatabaseSessionService(settings.ADK_DATABASE_URL)

    def create_agent(self):
        from send_money.adapters.agent.agent_definition import create_send_money_agent

        return create_send_money_agent(self)

    def create_app(self):
        """Return an ADK App with the agent and optional Langfuse plugin."""
        from google.adk.apps.app import App

        return App(
            name="send_money",
            root_agent=self.create_agent(),
            plugins=self._build_plugins(),
        )

    # ── Internal helpers ─────────────────────────────────────

    def _build_langfuse_client(self):
        from django.conf import settings

        if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
            return None

        # Wire ADK's OTel pipeline → Langfuse OTLP endpoint
        from send_money.adapters.observability.otel_setup import setup_langfuse_otel

        setup_langfuse_otel(
            langfuse_host=settings.LANGFUSE_HOST,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
        )

        from langfuse import Langfuse

        return Langfuse(
            host=settings.LANGFUSE_HOST,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
        )

    def _build_plugins(self) -> list:
        if self._langfuse_client is None:
            return []
        from send_money.adapters.observability.langfuse_plugin import LangfuseAuditPlugin

        return [LangfuseAuditPlugin(self._langfuse_client)]
