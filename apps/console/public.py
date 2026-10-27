"""
Contrato público do módulo `console` para consumidores externos.

O `intelligence` usa este contrato para:
    - Consultar se a execução é permitida (quota).
    - Executar uma chamada de IA de forma governada (`call_ai`).
    - Reportar uso (tokens, custo) ao Console, quando o chamador
      executa a IA fora da ponte `call_ai` — caso raro, mas
      preservado por compatibilidade.
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List

from apps.console.models import Provider, UsageMetric, UsageRecord
from apps.console.services import QuotaService
from apps.console.services.usage_record_service import UsageRecordService
from apps.console.services.ai_call_service import AICallService, AICallError

logger = logging.getLogger('console')

PROVIDER_KEY_OPENAI = 'openai'
METRIC_KEY_AI_CREDITS = 'ai.credits'


# =========================================================================
# QUOTA
# =========================================================================

def is_ai_execution_allowed(workspace) -> tuple:
    """
    Consulta a política de quota do workspace para 'ai.credits'.

    Retorna (allowed: bool, reason: str).
    Não levanta exceção para o chamador — devolve o estado.
    """
    try:
        result = QuotaService.check(workspace)
    except Exception as exc:
        logger.exception(
            'Falha ao consultar quota do workspace=%s', workspace.id,
        )
        return (False, f'quota_check_error: {exc}')

    return (result.allowed, result.status)


# =========================================================================
# EXECUÇÃO GOVERNADA
# =========================================================================

def call_ai(
    *,
    workspace,
    operation: str,
    provider_key: str,
    model: str,
    prompt_version: str,
    messages: List[Dict[str, Any]],
    images: Optional[List[Dict]] = None,
    response_format: str = 'json_object',
    request_id: str,
) -> Dict[str, Any]:
    """
    Executa uma chamada de IA de forma governada.

    Contrato para o chamador (tipicamente `intelligence`):

        response = console_public.call_ai(
            workspace=workspace,
            operation='intelligence.analysis',
            provider_key='openai',
            model='gpt-4o-mini',
            prompt_version='v1',
            messages=[...],
            images=[{'url': '...', 'mime_type': 'image/png'}],
            request_id=str(run.id),
        )

    Retorna:
        {
            'raw_content': str,
            'input_tokens': int,
            'output_tokens': int,
            'duration_ms': int,
            'usage_record_id': str | None,
            'provider_request_id': str,
            'currency': str,
            'estimated_cost': str | None,
        }

    Levanta `AICallError` em qualquer falha (quota, provider,
    transporte, chave ausente). NÃO engole erro para o chamador.

    Idempotente por (provider_key, request_id): se já existe
    UsageRecord com esse par, devolve payload reconstruído sem
    chamar o provider novamente.
    """
    return AICallService.call(
        workspace=workspace,
        operation=operation,
        provider_key=provider_key,
        model=model,
        prompt_version=prompt_version,
        messages=messages,
        images=images,
        response_format=response_format,
        request_id=request_id,
    )


# =========================================================================
# REPORTE DE USO (compatibilidade)
# =========================================================================

def report_ai_usage(
    *,
    workspace_id,
    input_tokens: int,
    output_tokens: int,
    model: str,
    prompt_version: str,
    request_id: str,
    estimated_cost: Optional[Decimal] = None,
    currency: str = 'USD',
) -> Optional[UsageRecord]:
    """
    Reporta o uso de IA ao Console via UsageRecordService.

    Este caminho é FALLBACK — para chamadores que executaram a IA
    por fora da ponte `call_ai` (ex: testes, scripts de migração).
    Em produção, prefira `call_ai`, que registra uso e log juntos.

    `request_id` DEVE ser único (ex: `AnalysisRun.id`) — idempotência.
    """
    provider = Provider.objects.filter(key=PROVIDER_KEY_OPENAI).first()
    if provider is None:
        logger.warning(
            "Provider '%s' não encontrado. Uso de IA não registrado.",
            PROVIDER_KEY_OPENAI,
        )
        return None

    metric = UsageMetric.objects.filter(key=METRIC_KEY_AI_CREDITS).first()
    if metric is None:
        logger.warning(
            "Métrica '%s' não encontrada. Uso de IA não registrado.",
            METRIC_KEY_AI_CREDITS,
        )
        return None

    total_tokens = int(input_tokens) + int(output_tokens)

    try:
        record = UsageRecordService.record(
            provider=provider,
            metric=metric,
            quantity=total_tokens,
            unit='token',
            workspace_id=workspace_id,
            request_id=request_id,
            operation=f'intelligence.analysis.{prompt_version}',
            model=model,
            metadata={
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
            },
        )
        return record
    except Exception:
        logger.exception(
            'Falha ao reportar uso de IA (request_id=%s)', request_id,
        )
        return None