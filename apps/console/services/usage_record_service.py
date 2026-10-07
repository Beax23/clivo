"""
UsageRecordService — porta de entrada para criação de UsageRecord.

REGRA ARQUITETURAL:
    A criação de UsageRecord NUNCA acontece via API pública.
    Só domínios/integrações internos podem chamar este service.

    O Console APENAS OBSERVA os UsageRecord via API read-only.

IDEMPOTÊNCIA:
    Se `request_id` for fornecido, funciona como chave de idempotência
    por provider. Chamar `record()` duas vezes com o mesmo request_id
    retorna o registro existente, não cria duplicata.

    A proteção é CONCORRÊNCIA-SEGURA:
        1. Tentativa rápida de leitura (evita lock desnecessário).
        2. Criação; se IntegrityError por constraint, busca o existente.
        3. Se o payload for materialmente inconsistente com o existente,
           levanta `IdempotencyConflictError`.

    A constraint única em (provider, request_id) é a garantia final.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.console.models import (
    Provider,
    ProviderConnection,
    ProviderContract,
    UsageMetric,
    UsageRecord,
)
from apps.console.services.cost_service import CostService


class IdempotencyConflictError(Exception):
    """
    Levantado quando o mesmo request_id chega com payload
    materialmente diferente do registro já existente.
    """
    pass


# Campos cujo valor é considerado material para comparação de idempotência.
# Se algum deles divergir entre a chamada e o registro existente,
# tratamos como conflito.
_MATERIAL_FIELDS = (
    'provider_id',
    'metric_id',
    'quantity',
    'unit',
    'workspace_id',
    'operation',
    'model',
)


class UsageRecordService:

    @staticmethod
    def record(
        provider: Provider,
        metric: UsageMetric,
        quantity,
        unit: str,
        occurred_at: Optional[datetime] = None,
        connection: Optional[ProviderConnection] = None,
        contract: Optional[ProviderContract] = None,
        workspace_id: Optional[str] = None,
        request_id: str = '',
        operation: str = '',
        model: str = '',
        metadata: Optional[dict] = None,
        status: str = 'success',
    ) -> UsageRecord:
        """
        Cria um UsageRecord e calcula o custo estimado.

        Se `request_id` não for vazio:
            - Se já existe registro com (provider, request_id), compara payload.
              - Payload igual → retorna o existente.
              - Payload diferente → levanta IdempotencyConflictError.
            - Se não existe, cria com proteção contra race.
        """
        moment = occurred_at or timezone.now()
        qty = Decimal(str(quantity)) if quantity is not None else Decimal('0')

        # Caminho rápido: já existe?
        if request_id:
            existing = UsageRecord.objects.filter(
                provider=provider,
                request_id=request_id,
            ).first()

            if existing is not None:
                UsageRecordService._assert_material_match(
                    existing=existing,
                    metric=metric,
                    quantity=qty,
                    unit=unit,
                    workspace_id=workspace_id,
                    operation=operation,
                    model=model,
                )
                return existing

        # Cria com proteção contra race
        cost, currency, _ = CostService.calculate_for_usage(
            provider=provider,
            metric=metric,
            quantity=qty,
            contract=contract,
            at=moment,
        )

        try:
            with transaction.atomic():
                record = UsageRecord.objects.create(
                    provider=provider,
                    connection=connection,
                    metric=metric,
                    workspace_id=workspace_id,
                    occurred_at=moment,
                    quantity=qty,
                    unit=unit,
                    request_id=request_id,
                    operation=operation,
                    model=model,
                    metadata=metadata or {},
                    estimated_cost=cost,
                    currency=currency,
                    status=status,
                )
            return record

        except IntegrityError:
            # Corrida: outro processo criou primeiro.
            # Rebusca o registro existente e compara payload.
            if not request_id:
                # Se não há request_id, IntegrityError não é
                # idempotência — é outra constraint. Re-levanta.
                raise

            existing = UsageRecord.objects.filter(
                provider=provider,
                request_id=request_id,
            ).first()

            if existing is None:
                # Algo estranho: IntegrityError sem existente.
                raise

            UsageRecordService._assert_material_match(
                existing=existing,
                metric=metric,
                quantity=qty,
                unit=unit,
                workspace_id=workspace_id,
                operation=operation,
                model=model,
            )
            return existing

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_material_match(
        existing: UsageRecord,
        metric: UsageMetric,
        quantity: Decimal,
        unit: str,
        workspace_id: Optional[str],
        operation: str,
        model: str,
    ) -> None:
        """
        Compara campos materiais entre o registro existente e a chamada
        atual. Se divergirem, levanta IdempotencyConflictError.
        """
        diffs = []

        if existing.metric_id != metric.id:
            diffs.append(f"metric: {existing.metric_id} != {metric.id}")

        if existing.quantity != quantity:
            diffs.append(f"quantity: {existing.quantity} != {quantity}")

        if (existing.unit or '') != (unit or ''):
            diffs.append(f"unit: {existing.unit} != {unit}")

        existing_ws = str(existing.workspace_id) if existing.workspace_id else ''
        current_ws = str(workspace_id) if workspace_id else ''
        if existing_ws != current_ws:
            diffs.append(f"workspace_id: {existing_ws} != {current_ws}")

        if (existing.operation or '') != (operation or ''):
            diffs.append(f"operation: {existing.operation} != {operation}")

        if (existing.model or '') != (model or ''):
            diffs.append(f"model: {existing.model} != {model}")

        if diffs:
            raise IdempotencyConflictError(
                'request_id já utilizado com payload materialmente diferente: '
                + '; '.join(diffs)
            )