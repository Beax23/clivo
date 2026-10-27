"""
Testa o worker processando dois jobs consecutivos e o segundo
run marcando o primeiro como stale.

`_call_ai_via_console` é mockado; o resto (AnalysisService, JobService,
StalenessService) roda de verdade.

O segundo run precisa gerar `input_hash` diferente do primeiro.
O `input_hash` é calculado ANTES da chamada à IA — o `raw_content`
do mock não entra nele. Para o run2 executar, mudamos o
`structure_snapshot` do briefing (que entra no `payload_hash`).
"""

import json
import pytest
from unittest.mock import patch


pytestmark = pytest.mark.django_db


def _fake_response(insights=None):
    insights = insights or [
        {
            'kind': 'desire',
            'content': 'Desejo real.',
            'confidence': 'fact',
            'evidences': [
                {
                    'source_type': 'client.context',
                    'source_ref': 'ref',
                },
            ],
        },
    ]
    return {
        'raw_content': json.dumps({'insights': insights}),
        'input_tokens': 50,
        'output_tokens': 20,
        'duration_ms': 5,
        'usage_record_id': None,
        'provider_request_id': 'req-worker',
    }


def _mutate_briefing_snapshot(briefing):
    """
    Muda o `structure_snapshot` do briefing entre runs.

    `AnalysisService._prepare_input` lê o snapshot do briefing via
    `briefings.public.get_briefing_snapshot(...)`. Como esse snapshot
    entra no `payload_hash` → `input_hash`, mudar o snapshot faz o
    segundo run executar em vez de ser considerado idempotente.
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


@patch('apps.intelligence.services.analysis_service.AnalysisService._call_ai_via_console')
@patch('apps.console.public.is_ai_execution_allowed', return_value=(True, 'ok'))
def test_worker_two_runs_marks_first_stale(
    mock_quota, mock_call_ai,
    workspace, client, briefing, analysis_job,
):
    from apps.intelligence.models import AnalysisJob, InsightItem
    from apps.intelligence.services import AnalysisService

    mock_call_ai.return_value = _fake_response()
    AnalysisService.execute(analysis_job)
    first_insight = InsightItem.objects.filter(
        kind='desire', is_stale=False,
    ).first()
    assert first_insight is not None

    # Muda o input para o run2 ter hash diferente.
    _mutate_briefing_snapshot(briefing)
    briefing.refresh_from_db()

    job2 = AnalysisJob.objects.create(
        workspace=workspace, client=client, briefing=briefing,
        target_kinds=[], data_version='v2',
        job_key='job-worker-2',
    )
    mock_call_ai.return_value = _fake_response([
        {
            'kind': 'desire',
            'content': 'Desejo real (v2).',
            'confidence': 'fact',
            'evidences': [
                {
                    'source_type': 'client.context',
                    'source_ref': 'ref',
                },
            ],
        },
    ])
    run2 = AnalysisService.execute(job2)

    # Sanidade: o run2 precisa ter executado, não sido considerado
    # idempotente.
    assert run2 is not None, (
        'Run2 não foi criado. O `input_hash` continua igual ao do '
        'run1 — verifique se `_mutate_briefing_snapshot` alterou '
        'o `structure_snapshot` do briefing corretamente.'
    )

    first_insight.refresh_from_db()
    assert first_insight.is_stale is True