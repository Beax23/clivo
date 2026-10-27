"""
Testes unitários de AnalysisService.

Todos mockam `_call_ai_via_console` — nenhuma chamada real ao
provider. O teste de integração real fica em
`test_analysis_integration.py` (opt-in).

Cobrem:
    - Sucesso: insights e evidências persistidos.
    - Idempotência por input_hash.
    - Staleness detection.
    - Budget bloqueado.
    - Análise parcial (target_kinds).
    - Rejeição de kind fora de target_kinds.
    - Rejeição de kind que exige evidência sem evidência.
"""

import json
import pytest
from unittest.mock import patch
from decimal import Decimal
from django.utils import timezone

from apps.intelligence.services import AnalysisService
from apps.intelligence.models import (
    AnalysisRun, InsightItem, InsightEvidence, InsightEvent,
)
from apps.intelligence.exceptions import (
    StaleAnalysisError, BudgetExceededError, AIResponseError,
)

pytestmark = pytest.mark.django_db


def _fake_ai_response(insights, input_tokens=100, output_tokens=50,
                      usage_record_id=None):
    return {
        'raw_content': json.dumps({'insights': insights}),
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'duration_ms': 10,
        'usage_record_id': usage_record_id,
        'provider_request_id': 'req-fake',
    }


# =========================================================================
# SUCESSO
# =========================================================================

@patch('apps.intelligence.services.analysis_service.AnalysisService._call_ai_via_console')
@patch('apps.console.public.is_ai_execution_allowed', return_value=(True, 'ok'))
def test_execute_success_persists_insights_and_evidences(
    mock_quota, mock_call_ai, analysis_job,
):
    mock_call_ai.return_value = _fake_ai_response([
        {
            'kind': InsightItem.KIND_SUMMARY_BRIEFING,
            'content': 'Resumo do briefing.',
            'confidence': InsightItem.CONFIDENCE_INTERPRETATION,
            'evidences': [
                {
                    'source_type': InsightEvidence.SOURCE_TYPE_CLIENT_CONTEXT,
                    'source_ref': str(analysis_job.client_id),
                },
            ],
        },
        {
            'kind': InsightItem.KIND_DESIRE,
            'content': 'Desejo X.',
            'confidence': InsightItem.CONFIDENCE_FACT,
            'evidences': [
                {
                    'source_type': InsightEvidence.SOURCE_TYPE_CLIENT_CONTEXT,
                    'source_ref': str(analysis_job.client_id),
                },
            ],
        },
    ])

    run = AnalysisService.execute(analysis_job)

    assert run is not None
    assert run.status == AnalysisRun.STATUS_COMPLETED
    assert run.input_tokens == 100
    assert run.output_tokens == 50
    assert InsightItem.objects.count() == 2
    desire = InsightItem.objects.get(kind=InsightItem.KIND_DESIRE)
    assert desire.evidences.count() == 1


# =========================================================================
# IDEMPOTÊNCIA
# =========================================================================

@patch('apps.intelligence.services.analysis_service.AnalysisService._call_ai_via_console')
@patch('apps.console.public.is_ai_execution_allowed', return_value=(True, 'ok'))
def test_execute_is_idempotent_for_same_input(
    mock_quota, mock_call_ai, analysis_job,
):
    mock_call_ai.return_value = _fake_ai_response([])
    run1 = AnalysisService.execute(analysis_job)
    assert run1 is not None
    assert run1.status == AnalysisRun.STATUS_COMPLETED

    run2 = AnalysisService.execute(analysis_job)
    assert run2 is None
    assert AnalysisRun.objects.count() == 1


# =========================================================================
# STALE
# =========================================================================

@patch('apps.intelligence.services.analysis_service.AnalysisService._call_ai_via_console')
@patch('apps.console.public.is_ai_execution_allowed', return_value=(True, 'ok'))
def test_stale_detection_uses_created_at_of_latest_event(
    mock_quota, mock_call_ai,
    analysis_job, workspace, client, briefing,
):
    """
    Cria um InsightEvent DEPOIS de criar o run (via service), mas
    ANTES de `_apply_ai_results`. O run deve ser marcado como stale.

    O insight de teste inclui evidência porque `summary.briefing`
    está em KINDS_REQUIRING_EVIDENCE. Sem isso, a validação rejeita
    antes de chegar na checagem de staleness — e o teste falha pelo
    motivo errado.
    """
    def _side_effect(run, input_data):
        InsightEvent.objects.create(
            workspace=workspace, client=client, briefing=briefing,
            source_kind='client.updated', occurrence_id='newer',
        )
        return _fake_ai_response([
            {
                'kind': InsightItem.KIND_SUMMARY_BRIEFING,
                'content': 'x',
                'confidence': InsightItem.CONFIDENCE_INTERPRETATION,
                'evidences': [
                    {
                        'source_type': InsightEvidence.SOURCE_TYPE_CLIENT_CONTEXT,
                        'source_ref': str(client.id),
                    },
                ],
            },
        ])

    mock_call_ai.side_effect = _side_effect

    with pytest.raises(StaleAnalysisError):
        AnalysisService.execute(analysis_job)

    assert InsightItem.objects.filter(run__job=analysis_job).count() == 0


# =========================================================================
# BUDGET
# =========================================================================

@patch('apps.console.public.is_ai_execution_allowed', return_value=(False, 'blocked'))
def test_budget_blocked(mock_quota, analysis_job):
    with pytest.raises(BudgetExceededError):
        AnalysisService.execute(analysis_job)


# =========================================================================
# ANÁLISE PARCIAL
# =========================================================================

@patch('apps.intelligence.services.analysis_service.AnalysisService._call_ai_via_console')
@patch('apps.console.public.is_ai_execution_allowed', return_value=(True, 'ok'))
def test_partial_analysis_accepts_only_target_kinds(
    mock_quota, mock_call_ai, analysis_job,
):
    analysis_job.target_kinds = [InsightItem.KIND_EXECUTIVE_SUMMARY]
    analysis_job.save(update_fields=['target_kinds'])

    mock_call_ai.return_value = _fake_ai_response([
        {
            'kind': InsightItem.KIND_EXECUTIVE_SUMMARY,
            'content': 'Síntese.',
            'confidence': InsightItem.CONFIDENCE_INTERPRETATION,
            'evidences': [
                {
                    'source_type': InsightEvidence.SOURCE_TYPE_CLIENT_CONTEXT,
                    'source_ref': str(analysis_job.client_id),
                },
            ],
        },
    ])

    run = AnalysisService.execute(analysis_job)
    assert run.status == AnalysisRun.STATUS_COMPLETED
    assert InsightItem.objects.filter(
        kind=InsightItem.KIND_EXECUTIVE_SUMMARY,
    ).count() == 1


@patch('apps.intelligence.services.analysis_service.AnalysisService._call_ai_via_console')
@patch('apps.console.public.is_ai_execution_allowed', return_value=(True, 'ok'))
def test_partial_analysis_rejects_kind_outside_target(
    mock_quota, mock_call_ai, analysis_job,
):
    analysis_job.target_kinds = [InsightItem.KIND_EXECUTIVE_SUMMARY]
    analysis_job.save(update_fields=['target_kinds'])

    mock_call_ai.return_value = _fake_ai_response([
        {
            'kind': InsightItem.KIND_DESIRE,
            'content': 'Desejo fora de escopo.',
            'confidence': InsightItem.CONFIDENCE_FACT,
            'evidences': [],
        },
    ])

    with pytest.raises(AIResponseError, match='não solicitado'):
        AnalysisService.execute(analysis_job)


# =========================================================================
# EVIDÊNCIA OBRIGATÓRIA
# =========================================================================

@patch('apps.intelligence.services.analysis_service.AnalysisService._call_ai_via_console')
@patch('apps.console.public.is_ai_execution_allowed', return_value=(True, 'ok'))
def test_kind_requiring_evidence_rejects_empty_evidences(
    mock_quota, mock_call_ai, analysis_job,
):
    mock_call_ai.return_value = _fake_ai_response([
        {
            'kind': InsightItem.KIND_DESIRE,
            'content': 'Sem evidência.',
            'confidence': InsightItem.CONFIDENCE_FACT,
            'evidences': [],
        },
    ])
    with pytest.raises(AIResponseError, match='evidência obrigatória'):
        AnalysisService.execute(analysis_job)