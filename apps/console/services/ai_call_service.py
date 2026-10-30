"""
AICallService — execução real e governada de uma chamada de IA.

RESPONSABILIDADES
-----------------
Este serviço é o ÚNICO ponto do sistema que efetivamente chama o
provider de IA. Ele:

    1. Verifica a política de quota do workspace (QuotaService).
    2. Resolve o Provider e (opcionalmente) o ProviderConnection.
    3. Executa a chamada real ao provider (openai / gemini / anthropic).
    4. Registra ProviderLog com status, latência, tokens, modelo,
       request_id e correlation_id.
    5. Cria UsageRecord idempotente (por request_id) com o custo
       calculado a partir do ProviderPricing VIGENTE naquele instante.
    6. Devolve um payload normalizado para o chamador.

IDEMPOTÊNCIA
------------
O `request_id` é a chave de idempotência. Se já existe um
`UsageRecord` com esse `request_id` para o mesmo provider, o
serviço NÃO chama o provider de novo.

O `raw_content` da resposta é persistido em
`UsageRecord.metadata['raw_content']` para que chamadas idempotentes
possam reconstruir a resposta sem chamar o provider novamente.
"""

import logging
import time
from decimal import Decimal
from typing import Optional, List, Dict, Any

from django.conf import settings

from apps.console.models import (
    Provider, ProviderConnection, UsageRecord, UsageMetric,
)
from apps.console.services.provider_log_service import ProviderLogService
from apps.console.services.usage_record_service import (
    UsageRecordService, IdempotencyConflictError,
)
from apps.console.exceptions import QuotaError

logger = logging.getLogger('console')


AI_METRIC_KEY = 'ai.credits'


class AICallError(Exception):
    """Falha controlada na execução da chamada de IA."""
    pass


class AICallService:

    @staticmethod
    def call(
        *,
        workspace,
        operation: str,
        provider_key: Optional[str] = None,
        model: Optional[str] = None,
        prompt_version: str,
        messages: List[Dict[str, Any]],
        images: Optional[List[Dict]] = None,
        response_format: str = 'json_object',
        request_id: str,
        connection: Optional[ProviderConnection] = None,
    ) -> Dict[str, Any]:
        if not request_id:
            raise AICallError('request_id é obrigatório (idempotência).')

        provider_key, model = AICallService._resolve_provider_and_model(
            provider_key=provider_key,
            model=model,
        )

        AICallService._assert_quota_allows(workspace)

        existing = AICallService._find_existing_usage(
            provider_key=provider_key, request_id=request_id,
        )
        if existing is not None:
            raw_saved = (existing.metadata or {}).get('raw_content')
            if raw_saved is None:
                logger.warning(
                    'call_ai idempotente SEM raw_content salvo '
                    '(request_id=%s, usage=%s). Registro antigo.',
                    request_id, existing.id,
                )
                return AICallService._build_response_from_existing(
                    existing, raw_fallback='',
                )
            logger.info(
                'call_ai idempotente: request_id=%s já registrado '
                '(usage=%s). Devolvendo raw_content salvo.',
                request_id, existing.id,
            )
            return AICallService._build_response_from_existing(
                existing, raw_fallback=raw_saved,
            )

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
            raise AICallError(f'Falha na chamada do provider: {exc}') from exc

        duration_ms = int((time.time() - started) * 1000)
        input_tokens = int(provider_result.get('input_tokens') or 0)
        output_tokens = int(provider_result.get('output_tokens') or 0)
        raw_content = provider_result.get('raw_content') or ''
        provider_request_id = provider_result.get('provider_request_id') or ''

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
                'Falha ao registrar ProviderLog (request=%s).',
                request_id,
            )

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
                    'raw_content': raw_content,
                },
                status='success',
            )
            estimated_cost_str = (
                str(usage_record.estimated_cost)
                if usage_record.estimated_cost is not None else None
            )
            currency = usage_record.currency or ''
        except IdempotencyConflictError as exc:
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
                raw_content = (usage_record.metadata or {}).get(
                    'raw_content', raw_content,
                )
        except Exception:
            logger.exception(
                'Falha ao criar UsageRecord (request=%s).',
                request_id,
            )

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
    # RESOLUÇÃO DE PROVIDER/MODEL
    # ==================================================================

    @staticmethod
    def _resolve_provider_and_model(
        *,
        provider_key: Optional[str],
        model: Optional[str],
    ) -> tuple:
        if provider_key and model:
            return provider_key, model

        try:
            from apps.console.services.ai_config_service import (
                AIConfigService,
            )
            config = AIConfigService.get_or_create_default()
        except Exception:
            config = None

        if config is not None and config.is_active:
            return (
                provider_key or config.provider.key,
                model or config.model,
            )

        return (
            provider_key or 'openai',
            model or getattr(settings, 'AI_MODEL', 'gpt-4o-mini'),
        )

    # ==================================================================
    # QUOTA
    # ==================================================================

    @staticmethod
    def _assert_quota_allows(workspace) -> None:
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
        return (
            UsageRecord.objects
            .filter(provider__key=provider_key, request_id=request_id)
            .select_related('provider', 'metric')
            .first()
        )

    @staticmethod
    def _build_response_from_existing(
        usage_record: UsageRecord,
        *,
        raw_fallback: str = '',
    ) -> Dict[str, Any]:
        metadata = usage_record.metadata or {}
        return {
            'raw_content': raw_fallback,
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
    # PROVIDER — despacho
    # ==================================================================

    @staticmethod
    def _call_provider(
        *,
        provider_key: str,
        model: str,
        messages: List[Dict],
        response_format: str,
    ) -> Dict[str, Any]:
        if provider_key == 'openai':
            return AICallService._call_openai(
                model=model,
                messages=messages,
                response_format=response_format,
            )
        if provider_key == 'gemini':
            return AICallService._call_gemini(
                model=model,
                messages=messages,
                response_format=response_format,
            )
        if provider_key == 'anthropic':
            return AICallService._call_anthropic(
                model=model,
                messages=messages,
                response_format=response_format,
            )
        raise AICallError(
            f'Provider "{provider_key}" sem adaptador implementado. '
            f'Suportados: openai, gemini, anthropic.'
        )

    # ==================================================================
    # ADAPTER — OpenAI
    # ==================================================================

    @staticmethod
    def _call_openai(
        *, model: str, messages: List[Dict], response_format: str,
    ) -> Dict[str, Any]:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AICallError(
                f'Biblioteca "openai" não instalada: {exc}'
            ) from exc

        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            raise AICallError('OPENAI_API_KEY não configurada no ambiente.')

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
    # ADAPTER — Gemini (google.genai)
    # ==================================================================

    @staticmethod
    def _call_gemini(
        *, model: str, messages: List[Dict], response_format: str,
    ) -> Dict[str, Any]:
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:
            raise AICallError(
                'Biblioteca "google-genai" não instalada. '
                'Rode `pip install google-genai` e remova o pacote '
                'antigo `google-generativeai` do requirements.'
            ) from exc

        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            raise AICallError('GEMINI_API_KEY não configurada no ambiente.')

        system_parts = [
            m['content'] for m in messages if m.get('role') == 'system'
        ]
        user_parts = []
        for m in messages:
            role = m.get('role')
            if role == 'system':
                continue
            content = m.get('content')
            if isinstance(content, str):
                user_parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get('type') == 'text':
                        user_parts.append(part.get('text') or '')
                    elif part.get('type') == 'image_url':
                        url = (part.get('image_url') or {}).get('url') or ''
                        if url:
                            user_parts.append(
                                genai_types.Part.from_uri(
                                    file_uri=url,
                                    mime_type=_guess_mime_from_url(url),
                                )
                            )

        client = genai.Client(api_key=api_key)

        config_kwargs = {
            'temperature': 0.2,
        }
        if system_parts:
            config_kwargs['system_instruction'] = '\n'.join(system_parts)
        if response_format == 'json_object':
            config_kwargs['response_mime_type'] = 'application/json'

        try:
            response = client.models.generate_content(
                model=model,
                contents=user_parts,
                config=genai_types.GenerateContentConfig(**config_kwargs),
            )
        except Exception as exc:
            msg = str(exc)
            if 'NOT_FOUND' in msg or '404' in msg or 'no longer available' in msg:
                raise AICallError(
                    f'O modelo "{model}" não está mais disponível no '
                    f'Gemini. Troque no Console: '
                    f'/console/ → IA → Provider ativo → Modelo. '
                    f'Mensagem do provider: {msg}'
                ) from exc
            raise AICallError(
                f'Falha na chamada ao Gemini: {exc}'
            ) from exc

        try:
            text = response.text or ''
        except Exception:
            text = ''
            for candidate in (getattr(response, 'candidates', None) or []):
                for part in (getattr(candidate, 'content', None) and
                             candidate.content.parts or []):
                    if getattr(part, 'text', None):
                        text += part.text

        usage = getattr(response, 'usage_metadata', None)
        input_tokens = int(getattr(usage, 'prompt_token_count', 0) or 0) if usage else 0
        output_tokens = int(
            getattr(usage, 'candidates_token_count', 0) or 0
        ) if usage else 0

        return {
            'raw_content': text,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'provider_request_id': '',
        }

    # ==================================================================
    # ADAPTER — Anthropic
    # ==================================================================

    @staticmethod
    def _call_anthropic(
        *, model: str, messages: List[Dict], response_format: str,
    ) -> Dict[str, Any]:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise AICallError(
                f'Biblioteca "anthropic" não instalada: {exc}'
            ) from exc

        api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
        if not api_key:
            raise AICallError('ANTHROPIC_API_KEY não configurada no ambiente.')

        client = Anthropic(api_key=api_key)

        system_parts = [
            m['content'] for m in messages if m.get('role') == 'system'
        ]
        user_messages = [
            {'role': m['role'], 'content': m['content']}
            for m in messages if m.get('role') != 'system'
        ]

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system='\n'.join(system_parts) if system_parts else '',
            messages=user_messages,
        )

        text_parts = []
        for block in response.content:
            if getattr(block, 'type', '') == 'text':
                text_parts.append(getattr(block, 'text', ''))
        text = ''.join(text_parts)

        usage = getattr(response, 'usage', None)
        input_tokens = getattr(usage, 'input_tokens', 0) if usage else 0
        output_tokens = getattr(usage, 'output_tokens', 0) if usage else 0

        return {
            'raw_content': text,
            'input_tokens': int(input_tokens or 0),
            'output_tokens': int(output_tokens or 0),
            'provider_request_id': getattr(response, 'id', '') or '',
        }

    # ==================================================================
    # MULTIMODAL
    # ==================================================================

    @staticmethod
    def _attach_images(
        messages: List[Dict], images: Optional[List[Dict]],
    ) -> List[Dict]:
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

        result = [dict(m) for m in messages]

        for i in range(len(result) - 1, -1, -1):
            if result[i].get('role') == 'user':
                existing = result[i].get('content')
                if isinstance(existing, str):
                    parts = [{'type': 'text', 'text': existing}]
                elif isinstance(existing, list):
                    parts = list(existing)
                else:
                    parts = []
                parts.extend(valid)
                result[i]['content'] = parts
                return result

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


def _guess_mime_from_url(url: str) -> str:
    lower = url.lower().split('?')[0]
    if lower.endswith('.png'):
        return 'image/png'
    if lower.endswith('.webp'):
        return 'image/webp'
    if lower.endswith('.gif'):
        return 'image/gif'
    return 'image/jpeg'