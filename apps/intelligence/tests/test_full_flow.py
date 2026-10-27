"""
Teste de integração PONTA A PONTA com `call_ai` mockado.

Cobre o fluxo completo exigido pela diretriz §6.

O que este teste NÃO prova:
    - Que a OpenAI responde. Isso é `test_analysis_integration.py`
      (opt-in).
    - Que a ponte `console.call_ai` funciona de verdade. O mock
      substitui `_call_ai_via_console`, que é a camada acima.
"""

import json
import pytest
from unittest.mock import patch
from decimal import Decimal
from django.utils import timezone


pytestmark = pytest.mark.django_db


# =========================================================================
# HELPERS
# =========================================================================

def _mock_ai_response(usage_record_id=None, insights=None):
    insights = insights or [
        {
            'kind': 'summary.briefing',
            'content': 'Resumo extraído do briefing.',
            'confidence': 'interpretation',
            'evidences': [
                {
                    'source_type': 'client.context',
                    'source_ref': 'fake-ref',
                },
            ],
        },
        {
            'kind': 'desire',
            'content': 'O cliente deseja integração com jardim.',
            'confidence': 'fact',
            'evidences': [
                {
                    'source_type': 'client.context',
                    'source_ref': 'fake-ref-2',
                },
            ],
        },
        {
            'kind': 'tag',
            'content': 'jardim',
            'confidence': 'fact',
            'evidences': [],
        },
    ]
    return {
        'raw_content': json.dumps({'insights': insights}),
        'input_tokens': 200,
        'output_tokens': 80,
        'duration_ms': 25,
        'usage_record_id': usage_record_id,
        'provider_request_id': 'req-flow-1',
    }


def _create_usage_record(workspace, request_id='req-flow-1'):
    """Cria um UsageRecord real para o teste de alocação de custo."""
    from apps.console.models import (
        Provider, UsageMetric, UsageRecord,
    )
    provider, _ = Provider.objects.get_or_create(
        key='openai',
        defaults={'name': 'OpenAI', 'category': 'ai', 'is_active': True},
    )
    metric, _ = UsageMetric.objects.get_or_create(
        key='ai.credits',
        defaults={
            'name': 'AI', 'unit': 'token',
            'kind': 'counter', 'origin': 'recorded',
        },
    )
    return UsageRecord.objects.create(
        provider=provider, metric=metric,
        workspace_id=workspace.id,
        occurred_at=timezone.now(),
        quantity=Decimal('280'),
        unit='token',
        estimated_cost=Decimal('0.00280000'),
        currency='USD',
        request_id=request_id,
    )


def _execute(job):
    from apps.intelligence.services import AnalysisService
    return AnalysisService.execute(job)


def _mutate_briefing_snapshot(briefing):
    """
    Muda o `structure_snapshot` do briefing entre runs.

    `AnalysisService._prepare_input` lê o snapshot do briefing via
    `briefings.public.get_briefing_snapshot(...)`. Como esse snapshot
    entra no `payload_hash`, e o `payload_hash` entra no `input_hash`,
    mudar o snapshot faz o segundo run gerar um `input_hash` diferente
    — e o `AnalysisService` executa de verdade em vez de ser
    considerado idempotente.
    """
    briefing.structure_snapshot = {
        'sections': [{
            'id': 's1',
            'title': 'Sobre você',
            'description': '',
            'position': 1,
            'questions': [{
                'id': 'q1',
                'text': 'Como você descreveria sua rotina?',
                'instructions': '',
                'question_type': 'text',
                'allowed_response_formats': ['text'],
                'options': [],
                'position': 1,
                'is_required': True,
                'reference_document_ids': [],
                'is_custom': False,
            }],
        }],
    }
    briefing.save(update_fields=['structure_snapshot', 'updated_at'])


# =========================================================================
# TESTES
# =========================================================================

@patch('apps.intelligence.services.analysis_service.AnalysisService._call_ai_via_console')
@patch('apps.console.public.is_ai_execution_allowed', return_value=(True, 'ok'))
class TestFullFlow:

    def test_insights_persisted_with_evidences_and_cost(
        self, mock_quota, mock_call_ai,
        workspace, client, briefing, analysis_job,
    ):
        usage_record = _create_usage_record(workspace)
        mock_call_ai.return_value = _mock_ai_response(
            usage_record_id=str(usage_record.id),
        )

        run = _execute(analysis_job)

        assert run is not None
        assert run.status == 'completed'

        from apps.intelligence.models import (
            InsightItem, InsightEvidence, InsightCostAllocation,
        )
        assert InsightItem.objects.filter(run=run).count() == 3

        desire = InsightItem.objects.get(run=run, kind='desire')
        assert desire.evidences.count() >= 1

        allocations = InsightCostAllocation.objects.filter(
            insight__run=run,
        )
        assert allocations.count() == 3
        total_allocated = sum(
            a.allocated_cost for a in allocations
            if a.allocated_cost is not None
        )
        # A soma bate EXATA com o custo real.
        assert total_allocated == Decimal('0.00280000')

    def test_containers_return_insights(
        self, mock_quota, mock_call_ai,
        workspace, client, briefing, analysis_job,
    ):
        usage_record = _create_usage_record(workspace)
        mock_call_ai.return_value = _mock_ai_response(
            usage_record_id=str(usage_record.id),
        )
        _execute(analysis_job)

        from apps.intelligence.services import ContainerService
        mesa = ContainerService.build_mesa(
            workspace=workspace, client=client,
        )
        assert mesa['counts']['01_desejos_prioridades'] >= 1
        assert mesa['counts']['05_resumo'] >= 1

        relatorio = ContainerService.build_relatorio(
            workspace=workspace, briefing=briefing,
        )
        assert relatorio['counts']['01_sintese_executiva'] == 0
        assert relatorio['counts']['02_desejos_criterios'] >= 1

    def test_second_run_marks_first_stale(
        self, mock_quota, mock_call_ai,
        workspace, client, briefing, analysis_job,
    ):
        """
        O segundo run precisa gerar `input_hash` diferente do primeiro.

        O `input_hash` é calculado ANTES da chamada à IA — o
        `raw_content` do mock não entra nele. O que entra é:
            - workspace_id
            - prompt_version, provider, model
            - payload_hash (do `_prepare_input`: snapshot do cliente
              + snapshot do briefing)
            - target_kinds

        Para o run2 executar de verdade, mudamos o `structure_snapshot`
        do briefing — ele entra no `payload_hash` via
        `get_briefing_snapshot`.

        Sem isso, o `AnalysisService._create_analysis_run` detecta
        idempotência por `input_hash` e retorna `None` — o
        `StalenessService` nunca é chamado, e o assert falha.
        """
        from apps.intelligence.models import AnalysisJob, InsightItem

        usage1 = _create_usage_record(workspace, request_id='req-flow-1')
        mock_call_ai.return_value = _mock_ai_response(
            usage_record_id=str(usage1.id),
        )
        _execute(analysis_job)
        first_desire = InsightItem.objects.get(
            kind='desire', is_stale=False,
        )
        assert first_desire.is_stale is False

        # Muda o input para o run2 ter hash diferente.
        _mutate_briefing_snapshot(briefing)
        briefing.refresh_from_db()

        job2 = AnalysisJob.objects.create(
            workspace=workspace, client=client, briefing=briefing,
            target_kinds=[], data_version='v2',
            job_key='job-flow-2',
        )
        usage2 = _create_usage_record(workspace, request_id='req-flow-2')
        mock_call_ai.return_value = _mock_ai_response(
            usage_record_id=str(usage2.id),
            insights=[
                {
                    'kind': 'summary.briefing',
                    'content': 'Resumo (v2) atualizado.',
                    'confidence': 'interpretation',
                    'evidences': [
                        {
                            'source_type': 'client.context',
                            'source_ref': 'fake-ref',
                        },
                    ],
                },
                {
                    'kind': 'desire',
                    'content': 'Desejo atualizado na v2.',
                    'confidence': 'fact',
                    'evidences': [
                        {
                            'source_type': 'client.context',
                            'source_ref': 'fake-ref-2',
                        },
                    ],
                },
                {
                    'kind': 'tag',
                    'content': 'jardim (v2)',
                    'confidence': 'fact',
                    'evidences': [],
                },
            ],
        )
        run2 = _execute(job2)

        # Sanidade: o run2 precisa ter executado, não sido considerado
        # idempotente. Se for None, o snapshot não mudou o suficiente.
        assert run2 is not None, (
            'Run2 não foi criado. O `input_hash` continua igual ao do '
            'run1 — verifique se `_mutate_briefing_snapshot` alterou '
            'o `structure_snapshot` do briefing corretamente.'
        )

        first_desire.refresh_from_db()
        assert first_desire.is_stale is True