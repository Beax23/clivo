"""
Testes do worker de Inteligência.

Cobrem:
    - Processar um job com sucesso.
    - Tratar falha do job.
    - `claim_next_job` ser exclusivo (sequencialmente).
    - `skip_locked` sob concorrência real (requer Postgres).

O teste de `skip_locked` real é skipado em SQLite em memória, mesmo
padrão do `apps/briefings/tests/test_concurrency.py`.
"""

import pytest
from unittest.mock import patch
from django.core.management import call_command

from apps.intelligence.models import AnalysisJob, AnalysisRun
from apps.intelligence.services import JobService

pytestmark = pytest.mark.django_db


def _running_on_postgres() -> bool:
    try:
        from django.db import connection
        return connection.vendor == 'postgresql'
    except Exception:
        return False


@patch('apps.intelligence.services.analysis_service.AnalysisService.execute')
def test_worker_processes_one_job(mock_execute, analysis_job):
    from unittest.mock import MagicMock
    mock_run = MagicMock()
    mock_run.status = AnalysisRun.STATUS_COMPLETED
    mock_run.id = 'fake-run'
    mock_execute.return_value = mock_run

    call_command('intelligence_worker', '--run-once')

    analysis_job.refresh_from_db()
    assert analysis_job.status == AnalysisJob.STATUS_COMPLETED
    mock_execute.assert_called_once()


@patch('apps.intelligence.services.analysis_service.AnalysisService.execute')
def test_worker_handles_job_failure(mock_execute, analysis_job):
    mock_execute.side_effect = Exception('AI failed')
    call_command('intelligence_worker', '--run-once')
    analysis_job.refresh_from_db()
    assert analysis_job.status == AnalysisJob.STATUS_FAILED
    assert 'AI failed' in analysis_job.last_error_message


def test_claim_next_job_is_exclusive(analysis_job):
    """
    Duas chamadas seguidas: a primeira retorna o job, a segunda retorna
    None (o job já foi marcado como processing).
    """
    j1 = JobService.claim_next_job()
    assert j1 is not None
    assert j1.id == analysis_job.id
    assert j1.status == AnalysisJob.STATUS_PROCESSING

    j2 = JobService.claim_next_job()
    assert j2 is None


@pytest.mark.skipif(
    not _running_on_postgres(),
    reason=(
        'Teste real de concorrência requer Postgres. '
        'SQLite em memória não compartilha o banco entre threads. '
        'Rode no CI com Postgres habilitado.'
    ),
)
def test_claim_skips_locked_rows(analysis_job, django_db_blocker):
    """
    Simula um worker que segura o lock. Um segundo worker rodando
    em outra conexão (thread) deve usar `skip_locked` e retornar
    None em vez de bloquear.
    """
    import threading
    import time
    results = []

    def hold_lock():
        from django.db import transaction
        with django_db_blocker.unblock():
            with transaction.atomic():
                AnalysisJob.objects.select_for_update().filter(
                    id=analysis_job.id
                ).first()
                time.sleep(1.5)

    def try_claim():
        from django.db import connection
        with django_db_blocker.unblock():
            try:
                j = JobService.claim_next_job()
                results.append(j)
            finally:
                connection.close()

    t1 = threading.Thread(target=hold_lock)
    t1.start()
    time.sleep(0.3)
    t2 = threading.Thread(target=try_claim)
    t2.start()
    t1.join()
    t2.join()

    # O segundo worker deve ter retornado None (skip_locked)
    assert len(results) == 1
    assert results[0] is None