"""
ProviderLogService — porta de entrada para criação de ProviderLog.

REGRA ARQUITETURAL:
    Igual a UsageRecord: só chamadas internas criam ProviderLog.
    O Console APENAS OBSERVA.

    ProviderLog é observabilidade. NÃO é fonte de custo oficial.
"""

from datetime import datetime
from typing import Optional

from django.utils import timezone

from apps.console.models import (
    Provider,
    ProviderConnection,
    ProviderLog,
)


class ProviderLogService:

    @staticmethod
    def log(
        provider: Provider,
        occurred_at: Optional[datetime] = None,
        connection: Optional[ProviderConnection] = None,
        workspace_id: Optional[str] = None,
        operation: str = '',
        model: str = '',
        status: str = 'success',
        latency_ms: Optional[int] = None,
        input_units: Optional[int] = None,
        output_units: Optional[int] = None,
        estimated_cost=None,
        currency: str = 'USD',
        request_id: str = '',
        correlation_id: str = '',
        error_message: str = '',
        metadata: Optional[dict] = None,
    ) -> ProviderLog:
        """Registra um log operacional de chamada a provider."""
        return ProviderLog.objects.create(
            provider=provider,
            connection=connection,
            workspace_id=workspace_id,
            occurred_at=occurred_at or timezone.now(),
            operation=operation,
            model=model,
            status=status,
            latency_ms=latency_ms,
            input_units=input_units,
            output_units=output_units,
            estimated_cost=estimated_cost,
            currency=currency,
            request_id=request_id,
            correlation_id=correlation_id,
            error_message=error_message,
            metadata=metadata or {},
        )