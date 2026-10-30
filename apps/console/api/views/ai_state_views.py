"""
AIStateViewSet — controle da IA no Console.

Endpoints:
    GET  /api/console/ai/
        Estado: provider/modelo ativos + contagens 30d.

    POST /api/console/ai/set-provider/
        body: {"provider_key": "openai", "model": "gpt-4o-mini"}

    POST /api/console/ai/set-active/
        body: {"is_active": true|false}

    GET  /api/console/ai/models/?provider=openai
        Lista modelos disponíveis na API do provider. Fallback estático
        se a lib não estiver instalada ou a chamada falhar.

    GET  /api/console/ai/costs/by-operation/?days=30
        Custo agrupado por operação.

    GET  /api/console/ai/costs/timeseries/?days=30
        Série diária.

    GET  /api/console/ai/tokens/by-model/?days=30
        Tokens por modelo.

    GET  /api/console/ai/logs/?status=&model=&operation=&days=&limit=
        Logs com filtros.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.console.models import Provider, ProviderLog, UsageRecord
from apps.console.permissions.console_permissions import IsConsoleAdmin
from apps.console.services.ai_config_service import AIConfigService


logger = logging.getLogger('console')

AI_METRIC_KEY = 'ai.credits'


# Fallback estático — usado quando a chamada à API do provider falha.
# Estes IDs refletem a documentação pública; a lista real pode variar.
STATIC_MODELS = {
    'openai': [
        {'id': 'gpt-4o-mini', 'label': 'GPT-4o Mini'},
        {'id': 'gpt-4o', 'label': 'GPT-4o'},
        {'id': 'gpt-4.1', 'label': 'GPT-4.1'},
        {'id': 'gpt-4.1-mini', 'label': 'GPT-4.1 Mini'},
        {'id': 'o4-mini', 'label': 'o4-mini'},
        {'id': 'o3', 'label': 'o3'},
    ],
    'gemini': [
        {'id': 'gemini-2.5-flash', 'label': 'Gemini 2.5 Flash'},
        {'id': 'gemini-2.5-flash-lite', 'label': 'Gemini 2.5 Flash-Lite'},
        {'id': 'gemini-2.5-pro', 'label': 'Gemini 2.5 Pro'},
        {'id': 'gemini-2.0-flash', 'label': 'Gemini 2.0 Flash'},
    ],
    'anthropic': [
        {'id': 'claude-sonnet-4-20250514', 'label': 'Claude Sonnet 4'},
        {'id': 'claude-3-5-haiku-20241022', 'label': 'Claude 3.5 Haiku'},
        {'id': 'claude-3-5-sonnet-20241022', 'label': 'Claude 3.5 Sonnet'},
    ],
}


def _parse_days(request) -> int:
    try:
        days = int(request.query_params.get('days', 30))
    except (TypeError, ValueError):
        days = 30
    return max(1, min(365, days))


def _list_openai_models() -> list:
    """Lista modelos da OpenAI via SDK. Levanta em caso de falha."""
    from openai import OpenAI

    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key:
        raise RuntimeError('OPENAI_API_KEY não configurada.')

    client = OpenAI(api_key=api_key)
    page = client.models.list()

    # Filtra apenas modelos de chat (heurística: IDs que contêm 'gpt' ou 'o').
    items = []
    for m in page.data:
        mid = getattr(m, 'id', '') or ''
        if not mid:
            continue
        # Inclui tudo que parece chat/completion. Exclui embeddings, tts, whisper.
        if any(prefix in mid for prefix in ('embedding', 'tts', 'whisper', 'dall-e')):
            continue
        items.append({'id': mid, 'label': mid})

    items.sort(key=lambda x: x['id'])
    return items


def _list_gemini_models() -> list:
    """Lista modelos do Gemini via SDK. Levanta em caso de falha."""
    import google.generativeai as genai

    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY não configurada.')

    genai.configure(api_key=api_key)

    items = []
    for m in genai.list_models():
        methods = getattr(m, 'supported_generation_methods', []) or []
        if 'generateContent' not in methods:
            continue
        name = getattr(m, 'name', '') or ''
        # Remove prefixo "models/"
        mid = name.split('/')[-1] if '/' in name else name
        if not mid:
            continue
        display = getattr(m, 'display_name', '') or mid
        items.append({'id': mid, 'label': display})

    items.sort(key=lambda x: x['id'])
    return items


def _list_anthropic_models() -> list:
    """Lista modelos da Anthropic via SDK. Levanta em caso de falha."""
    from anthropic import Anthropic

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY não configurada.')

    client = Anthropic(api_key=api_key)
    response = client.models.list()

    items = []
    for m in response.data:
        mid = getattr(m, 'id', '') or ''
        if not mid:
            continue
        display = getattr(m, 'display_name', '') or mid
        items.append({'id': mid, 'label': display})

    items.sort(key=lambda x: x['id'])
    return items


_MODEL_LISTERS = {
    'openai': _list_openai_models,
    'gemini': _list_gemini_models,
    'anthropic': _list_anthropic_models,
}


class AIStateViewSet(viewsets.ViewSet):

    permission_classes = [IsAuthenticated, IsConsoleAdmin]

    # ------------------------------------------------------------------
    # STATE
    # ------------------------------------------------------------------

    def list(self, request):
        try:
            config = AIConfigService.get_or_create_default()
            config_error = None
        except Exception as exc:
            config = None
            config_error = str(exc)

        available = list(
            Provider.objects
            .filter(category='ai')
            .order_by('name')
            .values('key', 'name', 'is_active')
        )

        start = timezone.now() - timedelta(days=30)

        logs_qs = ProviderLog.objects.filter(
            occurred_at__gte=start,
            provider__category='ai',
        )
        requests_30d = logs_qs.count()
        failed_30d = logs_qs.filter(
            status__in=['failed', 'timeout', 'rate_limited']
        ).count()

        cost_30d = (
            UsageRecord.objects
            .filter(
                occurred_at__gte=start,
                metric__key=AI_METRIC_KEY,
            )
            .aggregate(t=Sum('estimated_cost'))
            .get('t')
        )

        return Response({
            'config': None if config is None else {
                'provider_key': config.provider.key,
                'provider_name': config.provider.name,
                'model': config.model,
                'is_active': config.is_active,
                'updated_at': config.updated_at.isoformat(),
                'updated_by_email': (
                    config.updated_by.email if config.updated_by else None
                ),
            },
            'config_error': config_error,
            'available_providers': available,
            'usage_30d': {
                'requests': requests_30d,
                'failed': failed_30d,
                'error_rate_pct': (
                    round((failed_30d / requests_30d) * 100, 2)
                    if requests_30d else 0.0
                ),
                'total_cost': str(cost_30d or 0),
            },
        })

    # ------------------------------------------------------------------
    # SET PROVIDER
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='set-provider')
    def set_provider(self, request):
        provider_key = (request.data.get('provider_key') or '').strip()
        model = (request.data.get('model') or '').strip()

        if not provider_key:
            return Response(
                {'error': 'O campo "provider_key" é obrigatório.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not model:
            return Response(
                {'error': 'O campo "model" é obrigatório.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            config = AIConfigService.set_provider(
                provider_key=provider_key,
                model=model,
                actor=request.user,
            )
        except ValueError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'provider_key': config.provider.key,
            'provider_name': config.provider.name,
            'model': config.model,
            'is_active': config.is_active,
            'updated_at': config.updated_at.isoformat(),
        })

    # ------------------------------------------------------------------
    # SET ACTIVE
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='set-active')
    def set_active(self, request):
        is_active = request.data.get('is_active')
        if not isinstance(is_active, bool):
            return Response(
                {'error': 'O campo "is_active" deve ser booleano.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            config = AIConfigService.set_active(
                is_active=is_active, actor=request.user,
            )
        except Exception as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'provider_key': config.provider.key,
            'provider_name': config.provider.name,
            'model': config.model,
            'is_active': config.is_active,
            'updated_at': config.updated_at.isoformat(),
        })

    # ------------------------------------------------------------------
    # LIST MODELS
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='models')
    def models(self, request):
        """
        Lista modelos disponíveis na API do provider.

        Se a chamada falhar (sem API key, sem lib, erro de rede),
        devolve a lista estática + `source: 'static'`.
        """
        provider_key = (request.query_params.get('provider') or '').strip()

        if not provider_key:
            return Response(
                {'error': 'O parâmetro "provider" é obrigatório.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lister = _MODEL_LISTERS.get(provider_key)
        if lister is None:
            return Response(
                {
                    'provider': provider_key,
                    'models': STATIC_MODELS.get(provider_key, []),
                    'source': 'static',
                    'warning': f'Provider "{provider_key}" sem lister dinâmico. '
                               f'Usando lista estática.',
                },
                status=status.HTTP_200_OK,
            )

        try:
            models_list = lister()
            source = 'api'
            warning = None
        except Exception as exc:
            logger.warning(
                'Falha ao listar modelos de %s: %s. Usando fallback.',
                provider_key, exc,
            )
            models_list = STATIC_MODELS.get(provider_key, [])
            source = 'static'
            warning = f'Não foi possível consultar a API: {exc}'

        return Response({
            'provider': provider_key,
            'models': models_list,
            'source': source,
            'warning': warning,
        })

    # ------------------------------------------------------------------
    # COSTS BY OPERATION (agrupado, didático)
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='costs/by-operation')
    def costs_by_operation(self, request):
        days = _parse_days(request)
        start = timezone.now() - timedelta(days=days)

        rows = (
            UsageRecord.objects
            .filter(
                occurred_at__gte=start,
                metric__key=AI_METRIC_KEY,
            )
            .values('operation', 'provider__key', 'provider__name')
            .annotate(
                total=Sum('estimated_cost'),
                count=Count('id'),
                tokens=Sum('quantity'),
            )
            .order_by('-total')
        )

        return Response({
            'period_days': days,
            'results': [
                {
                    'operation': r['operation'] or '(sem operação)',
                    'provider_key': r['provider__key'],
                    'provider_name': r['provider__name'],
                    'total_cost': str(r['total'] or 0),
                    'count': r['count'],
                    'tokens': str(r['tokens'] or 0),
                }
                for r in rows
            ],
        })

    # ------------------------------------------------------------------
    # TIMESERIES
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='costs/timeseries')
    def costs_timeseries(self, request):
        days = _parse_days(request)
        start = timezone.now() - timedelta(days=days)

        rows = (
            UsageRecord.objects
            .filter(
                occurred_at__gte=start,
                metric__key=AI_METRIC_KEY,
            )
            .annotate(day=TruncDate('occurred_at'))
            .values('day')
            .annotate(
                total=Sum('estimated_cost'),
                tokens=Sum('quantity'),
                count=Count('id'),
            )
            .order_by('day')
        )

        return Response({
            'period_days': days,
            'results': [
                {
                    'day': r['day'].isoformat() if r['day'] else None,
                    'cost': str(r['total'] or 0),
                    'tokens': str(r['tokens'] or 0),
                    'count': r['count'],
                }
                for r in rows
            ],
        })

    # ------------------------------------------------------------------
    # TOKENS BY MODEL
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='tokens/by-model')
    def tokens_by_model(self, request):
        days = _parse_days(request)
        start = timezone.now() - timedelta(days=days)

        rows = (
            UsageRecord.objects
            .filter(
                occurred_at__gte=start,
                metric__key=AI_METRIC_KEY,
            )
            .values('model', 'provider__key')
            .annotate(
                tokens=Sum('quantity'),
                cost=Sum('estimated_cost'),
                count=Count('id'),
            )
            .order_by('-tokens')
        )

        return Response({
            'period_days': days,
            'results': [
                {
                    'model': r['model'] or '(desconhecido)',
                    'provider_key': r['provider__key'],
                    'tokens': str(r['tokens'] or 0),
                    'cost': str(r['cost'] or 0),
                    'count': r['count'],
                }
                for r in rows
            ],
        })

    # ------------------------------------------------------------------
    # LOGS
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='logs')
    def logs(self, request):
        days = _parse_days(request)
        start = timezone.now() - timedelta(days=days)

        qs = (
            ProviderLog.objects
            .filter(
                occurred_at__gte=start,
                provider__category='ai',
            )
            .select_related('provider', 'connection')
            .order_by('-occurred_at')
        )

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        model_filter = request.query_params.get('model')
        if model_filter:
            qs = qs.filter(model=model_filter)

        operation = request.query_params.get('operation')
        if operation:
            qs = qs.filter(operation=operation)

        try:
            limit = int(request.query_params.get('limit', 100))
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(500, limit))

        qs = list(qs[:limit])

        return Response({
            'period_days': days,
            'count': len(qs),
            'results': [
                {
                    'id': str(log.id),
                    'provider_key': log.provider.key,
                    'provider_name': log.provider.name,
                    'operation': log.operation,
                    'model': log.model,
                    'status': log.status,
                    'latency_ms': log.latency_ms,
                    'input_units': log.input_units,
                    'output_units': log.output_units,
                    'estimated_cost': (
                        str(log.estimated_cost)
                        if log.estimated_cost is not None else None
                    ),
                    'currency': log.currency or '',
                    'error_message': log.error_message or '',
                    'request_id': log.request_id or '',
                    'occurred_at': log.occurred_at.isoformat(),
                }
                for log in qs
            ],
        })