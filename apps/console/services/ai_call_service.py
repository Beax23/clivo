"""
AICallService — execução real e governada de uma chamada de IA.

RESPONSABILIDADES
-----------------
Este serviço é o ÚNICO ponto do sistema que efetivamente chama o
provider de IA. Ele:

    1. Verifica a política de quota do workspace (QuotaService).
    2. Resolve o Provider e (opcionalmente) o ProviderConnection.
    3. Executa a chamada real ao provider (OpenAI hoje; o provider
       é resolvido por key, então a porta está aberta para outros).
    4. Registra ProviderLog com status, latência, tokens, modelo,
       request_id e correlation_id.
    5. Cria UsageRecord idempotente (por request_id) com o custo
       calculado a partir do ProviderPricing VIGENTE naquele instante.
    6. Devolve um payload normalizado para o chamador (o módulo
       `intelligence`).

O QUE ESTE SERVIÇO NÃO FAZ
--------------------------
- NÃO monta prompt de domínio (isso é de `intelligence`).
- NÃO interpreta o conteúdo devolvido (isso é de `intelligence`).
- NÃO persiste insights (isso é de `intelligence`).

GOVERNANÇA
----------
A checagem de quota é feita ANTES da chamada. Se a política bloquear,
`AIProviderError` sobe sem custo — nenhuma chamada é feita, nenhum
UsageRecord é criado.

IDEMPOTÊNCIA
------------
O `request_id` (fornecido pelo chamador, tipicamente `AnalysisRun.id`)
é a chave. Se já existe um `UsageRecord` com esse `request_id` para
o mesmo provider, o serviço NÃO chama o provider de novo — devolve
o payload do registro existente via `_build_response_from_existing`.
Isso protege contra retries após falha parcial (chamada feita,
resposta recebida, mas processo caiu antes do commit).

O QUE ACONTECE SE A CHAMADA FOR COBRADA MAS FALHAR
--------------------------------------------------
- Se a exceção veio do provider (timeout, rate limit), não há como
  saber com certeza se cobrou. Registramos `ProviderLog` com
  `status='timeout'/'failed'` e NÃO criamos `UsageRecord`. A
  reconciliação é responsabilidade humana: o Console deve permitir
  ao operador criar o `UsageRecord` manualmente se a fatura do
  provider confirmar a cobrança. Não inventamos custo.

MULTIMODAL
----------
`images` é uma lista de `{'url': str, 'mime_type': str, ...}`.
Hoje só URLs `http(s)` são aceitas (padrão OpenAI). Se um item vier
sem URL ou com esquema inválido, ele é descartado com log — não
inventamos descrição de imagem.
"""

import logging
import time
from decimal import Decimal
from typing import Optional, List, Dict, Any

from django.conf import settings
from django.utils import timezone

from apps.console.models import (
    Provider, ProviderConnection, UsageRecord, UsageMetric,
)
from apps.console.services.provider_log_service import ProviderLogService
from apps.console.services.usage_record_service import (
    UsageRecordService, IdempotencyConflictError,
)
from apps.console.services.cost_service import CostService
from apps.console.exceptions import QuotaError

logger = logging.getLogger('console')


# Chave canônica da métrica de IA (definida pelo seed do Console).
AI_METRIC_KEY = 'ai.credits'


class AICallError(Exception):
    """Falha controlada na execução da chamada de IA."""
    pass


class AICallService:

    # ==================================================================
    # API PÚBLICA
    # ==================================================================

    @staticmethod
    def call(
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
        connection: Optional[ProviderConnection] = None,
    ) -> Dict[str, Any]:
        """
        Executa uma chamada de IA de forma governada.

        Args:
            workspace: Workspace dono da execução (para quota e custo).
            operation: identificador da operação (ex: 'intelligence.analysis').
            provider_key: chave do provider no Console (ex: 'openai').
            model: nome do modelo (ex: 'gpt-4o-mini').
            prompt_version: versão do prompt, para auditoria.
            messages: lista de mensagens no formato Chat Completions.
            images: lista opcional de imagens a anexar à última mensagem
                    do user. Cada item: {'url': str, 'mime_type': str}.
            response_format: 'json_object' ou 'text'.
            request_id: chave de idempotência (obrigatória).

        Returns:
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

        Raises:
            AICallError: em qualquer falha (quota, provider, parse).
        """
        if not request_id:
            raise AICallError('request_id é obrigatório (idempotência).')

        # ------------------------------------------------------------------
        # 1. Quota (antes de qualquer chamada)
        # ------------------------------------------------------------------
        AICallService._assert_quota_allows(workspace)

        # ------------------------------------------------------------------
        # 2. Idempotência: já foi registrado?
        # ------------------------------------------------------------------
        existing = AICallService._find_existing_usage(
            provider_key=provider_key, request_id=request_id,
        )
        if existing is not None:
            logger.info(
                'call_ai idempotente: request_id=%s já registrado '
                '(usage=%s). Pulando chamada ao provider.',
                request_id, existing.id,
            )
            return AICallService._build_response_from_existing(existing)

        # ------------------------------------------------------------------
        # 3. Provider e modelo de custo
        # ------------------------------------------------------------------
        provider = Provider.objects.filter(key=provider_key).first()
        if provider is None:
            raise AICallError(
                f'Provider "{provider_key}" não está cadastrado no Console.'
            )
        if not provider.is_active:
            raise AICallError(
                f'Provider "{provider_key}" está inativo no Console.'
            )

        metric = UsageMetric.objects.filter(
            key=AI_METRIC_KEY, is_active=True,
        ).first()
        if metric is None:
            raise AICallError(
                f'Métrica "{AI_METRIC_KEY}" não está ativa no catálogo '
                f'do Console. Rode `python manage.py seed_usage_metrics`.'
            )

        # ------------------------------------------------------------------
        # 4. Execução real
        # ------------------------------------------------------------------
        messages_with_images = AICallService._attach_images(messages, images)

        started = time.time()
        try:
            provider_result = AICallService._call_provider(
                provider_key=provider_key,
                model=model,
                messages=messages_with_images,
                response_format=response_format,
            )
        except Exception as exc:
            duration_ms = int((time.time() - started) * 1000)
            AICallService._log_failed(
                provider=provider,
                connection=connection,
                workspace=workspace,
                operation=operation,
                model=model,
                duration_ms=duration_ms,
                error_message=str(exc),
                request_id=request_id,
            )
            # Falha de provider NÃO cria UsageRecord: não sabemos se
            # houve cobrança. Reconciliação é humana.
            raise AICallError(f'Falha na chamada do provider: {exc}') from exc

        duration_ms = int((time.time() - started) * 1000)
        input_tokens = int(provider_result.get('input_tokens') or 0)
        output_tokens = int(provider_result.get('output_tokens') or 0)
        raw_content = provider_result.get('raw_content') or ''
        provider_request_id = provider_result.get('provider_request_id') or ''

        # ------------------------------------------------------------------
        # 5. ProviderLog (sucesso)
        # ------------------------------------------------------------------
        try:
            ProviderLogService.log(
                provider=provider,
                connection=connection,
                workspace_id=workspace.id,
                operation=operation,
                model=model,
                status='success',
                latency_ms=duration_ms,
                input_units=input_tokens,
                output_units=output_tokens,
                request_id=request_id,
                correlation_id=provider_request_id,
                metadata={'prompt_version': prompt_version},
            )
        except Exception:
            logger.exception(
                'Falha ao registrar ProviderLog (request=%s). A chamada '
                'prossegue — o log é auditoria, não bloqueia.',
                request_id,
            )

        # ------------------------------------------------------------------
        # 6. UsageRecord (idempotente por request_id)
        # ------------------------------------------------------------------
        total_units = input_tokens + output_tokens
        usage_record = None
        estimated_cost_str: Optional[str] = None
        currency = ''

        try:
            usage_record = UsageRecordService.record(
                provider=provider,
                metric=metric,
                quantity=Decimal(total_units),
                unit='token',
                connection=connection,
                workspace_id=workspace.id,
                request_id=request_id,
                operation=operation,
                model=model,
                metadata={
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'prompt_version': prompt_version,
                    'provider_request_id': provider_request_id,
                },
                status='success',
            )
            estimated_cost_str = (
                str(usage_record.estimated_cost)
                if usage_record.estimated_cost is not None else None
            )
            currency = usage_record.currency or ''
        except IdempotencyConflictError as exc:
            # Corrida: outra requisição criou o registro no meio-tempo.
            # Rebusca e devolve o existente.
            logger.warning(
                'IdempotencyConflictError em call_ai (request=%s): %s. '
                'Rebuscando registro existente.',
                request_id, exc,
            )
            usage_record = AICallService._find_existing_usage(
                provider_key=provider_key, request_id=request_id,
            )
            if usage_record is not None:
                estimated_cost_str = (
                    str(usage_record.estimated_cost)
                    if usage_record.estimated_cost is not None else None
                )
                currency = usage_record.currency or ''
        except Exception:
            logger.exception(
                'Falha ao criar UsageRecord (request=%s). A chamada foi '
                'feita e cobrada; a contabilização ficou pendente. '
                'Reconciliação humana necessária.',
                request_id,
            )
            # NÃO levanta: a resposta já existe e o chamador (intelligence)
            # precisa persistir os insights. Custo fica desconhecido.

        return {
            'raw_content': raw_content,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'duration_ms': duration_ms,
            'usage_record_id': (
                str(usage_record.id) if usage_record else None
            ),
            'provider_request_id': provider_request_id,
            'currency': currency,
            'estimated_cost': estimated_cost_str,
        }

    # ==================================================================
    # QUOTA
    # ==================================================================

    @staticmethod
    def _assert_quota_allows(workspace) -> None:
        """
        Consulta o QuotaService. Se a política bloquear, levanta
        AICallError ANTES de qualquer chamada ao provider.

        Reusa `apps.console.public.is_ai_execution_allowed` indiretamente:
        chamamos `QuotaService.check` diretamente aqui porque já estamos
        dentro do app `console` e precisamos do resultado estruturado
        para a mensagem de erro.
        """
        from apps.console.services.quota_service import QuotaService
        try:
            result = QuotaService.check(workspace)
        except QuotaError as exc:
            raise AICallError(f'Quota indisponível: {exc}') from exc

        if not result.allowed:
            raise AICallError(
                f'Execução de IA bloqueada pela quota do workspace '
                f'(status={result.status}, usado={result.used_bytes}B, '
                f'quota={result.quota_bytes}B).'
            )

    # ==================================================================
    # IDEMPOTÊNCIA
    # ==================================================================

    @staticmethod
    def _find_existing_usage(*, provider_key: str, request_id: str):
        """
        Busca um UsageRecord com o mesmo (provider_key, request_id).

        Retorna None se não existir.
        """
        return UsageRecord.objects.filter(
            provider__key=provider_key,
            request_id=request_id,
        ).select_related('provider', 'metric').first()

    @staticmethod
    def _build_response_from_existing(usage_record: UsageRecord) -> Dict[str, Any]:
        """
        Reconstrói o payload a partir de um UsageRecord existente.

        `raw_content` NÃO é recuperável (não armazenamos a resposta
        bruta do provider por política). Devolvemos string vazia.
        O chamador (intelligence) deve tratar como "resposta já
        persistida em run anterior" — o `AnalysisService` já detecta
        run concluído por `input_hash` e retorna None antes de chegar
        a esta situação. Este caminho existe apenas para robustez.
        """
        metadata = usage_record.metadata or {}
        return {
            'raw_content': '',
            'input_tokens': int(metadata.get('input_tokens') or 0),
            'output_tokens': int(metadata.get('output_tokens') or 0),
            'duration_ms': 0,
            'usage_record_id': str(usage_record.id),
            'provider_request_id': metadata.get('provider_request_id') or '',
            'currency': usage_record.currency or '',
            'estimated_cost': (
                str(usage_record.estimated_cost)
                if usage_record.estimated_cost is not None else None
            ),
        }

    # ==================================================================
    # PROVIDER
    # ==================================================================

    @staticmethod
    def _call_provider(
        *,
        provider_key: str,
        model: str,
        messages: List[Dict],
        response_format: str,
    ) -> Dict[str, Any]:
        """
        Executa a chamada real ao provider.

        Hoje só `openai` está implementado. Qualquer outra key levanta
        AICallError com mensagem clara — não fingimos suporte.
        """
        if provider_key == 'openai':
            return AICallService._call_openai(
                model=model, messages=messages, response_format=response_format,
            )
        raise AICallError(
            f'Provider "{provider_key}" não tem adaptador de execução '
            f'implementado. Providers suportados: openai.'
        )

    @staticmethod
    def _call_openai(
        *, model: str, messages: List[Dict], response_format: str,
    ) -> Dict[str, Any]:
        """
        Adaptador OpenAI. Não instancia o cliente se faltar chave.
        """
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AICallError(
                f'Biblioteca "openai" não instalada: {exc}'
            ) from exc

        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            raise AICallError(
                'OPENAI_API_KEY não configurada no ambiente.'
            )

        client = OpenAI(api_key=api_key)

        kwargs = {
            'model': model,
            'messages': messages,
            'temperature': 0.2,
        }
        if response_format == 'json_object':
            kwargs['response_format'] = {'type': 'json_object'}

        response = client.chat.completions.create(**kwargs)

        content = response.choices[0].message.content or ''
        usage = getattr(response, 'usage', None)
        input_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
        output_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
        provider_request_id = getattr(response, 'id', '') or ''

        return {
            'raw_content': content,
            'input_tokens': int(input_tokens),
            'output_tokens': int(output_tokens),
            'provider_request_id': str(provider_request_id),
        }

    # ==================================================================
    # MULTIMODAL
    # ==================================================================

    @staticmethod
    def _attach_images(
        messages: List[Dict], images: Optional[List[Dict]],
    ) -> List[Dict]:
        """
        Anexa imagens à última mensagem do user, no formato OpenAI:

            content: [
                {'type': 'text', 'text': '...'},
                {'type': 'image_url', 'image_url': {'url': '...'}},
            ]

        Regras:
            - Se não há imagens, devolve as mensagens como estão.
            - Se não há mensagem do user, devolve como está (não inventa).
            - Itens de imagem sem URL http(s) são descartados com log.
            - Não inventa descrição a partir de ID.
        """
        if not images:
            return messages

        valid = []
        for img in images:
            url = (img or {}).get('url') or ''
            if not url.startswith(('http://', 'https://')):
                logger.warning(
                    'Imagem descartada (URL inválida ou não-http): %s',
                    url or '<vazio>',
                )
                continue
            valid.append({'type': 'image_url', 'image_url': {'url': url}})

        if not valid:
            return messages

        # Copia rasa para não mutar o chamador.
        result = [dict(m) for m in messages]

        # Encontra a última mensagem do user.
        for i in range(len(result) - 1, -1, -1):
            if result[i].get('role') == 'user':
                existing_content = result[i].get('content')
                if isinstance(existing_content, str):
                    parts = [{'type': 'text', 'text': existing_content}]
                elif isinstance(existing_content, list):
                    parts = list(existing_content)
                else:
                    parts = []
                parts.extend(valid)
                result[i]['content'] = parts
                return result

        # Nenhuma mensagem do user? Devolve como veio, sem inventar.
        logger.warning(
            'Imagens presentes mas nenhuma mensagem do user nas mensagens '
            '— imagens não anexadas.'
        )
        return messages

    # ==================================================================
    # LOG DE FALHA
    # ==================================================================

    @staticmethod
    def _log_failed(
        *,
        provider: Provider,
        connection: Optional[ProviderConnection],
        workspace,
        operation: str,
        model: str,
        duration_ms: int,
        error_message: str,
        request_id: str,
    ) -> None:
        """
        Registra ProviderLog de falha. Best-effort.
        """
        try:
            ProviderLogService.log(
                provider=provider,
                connection=connection,
                workspace_id=workspace.id,
                operation=operation,
                model=model,
                status='failed',
                latency_ms=duration_ms,
                request_id=request_id,
                error_message=error_message[:2000],
            )
        except Exception:
            logger.exception(
                'Falha ao registrar ProviderLog de falha (request=%s).',
                request_id,
            )