"""Audit log repository — writes to the transfer_audit_logs table."""
from __future__ import annotations

from typing import Optional

from asgiref.sync import sync_to_async

from send_money.domain.repositories import AuditLogRepository


class DjangoAuditLogRepository(AuditLogRepository):
    async def log(
        self,
        transfer_id: str,
        session_id: str,
        user_id: str,
        action: str,
        langfuse_trace_id: str = "",
        langfuse_observation_id: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        @sync_to_async
        def _write() -> None:
            from send_money.adapters.persistence.django_models import TransferAuditLog

            TransferAuditLog.objects.create(
                transfer_id=transfer_id,
                session_id=session_id,
                user_id=user_id,
                action=action,
                langfuse_trace_id=langfuse_trace_id,
                langfuse_observation_id=langfuse_observation_id,
                metadata=metadata or {},
            )

        await _write()
