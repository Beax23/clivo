"""
Testes do sinal pre_delete em Briefing.

Estratégia:
    NÃO usamos `django_capture_on_commit_callbacks(execute=False)`,
    porque ele não captura de forma confiável callbacks registrados
    via `transaction.on_commit` em `pytest.mark.django_db`.

    Em vez disso, executamos manualmente os callbacks pendentes,
    acessando `connection.run_on_commit` diretamente. Isso testa
    o MESMO caminho que o Django executaria no commit real.

IMPORTANTE:
    `_run_pending_on_commit` NÃO engole exceções. Se o callback
    falhar, a exceção sobe para o teste — o teste falha com o
    traceback real do callback, não com um assert confuso.

    O formato de cada entrada de `run_on_commit` varia entre versões
    do Django:
        - Django < 6.x: (sids, callback)
        - Django 6.x+:  (sids, robust, callback)
    Por isso extraímos o callback via `_get_callback`, que pega o
    último callable da tupla — funciona em ambos.
"""

import pytest
from unittest.mock import patch
from django.db import connection


@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS', slug='ws-del')


@pytest.fixture
def client(db, workspace):
    from apps.clients.models import Client
    return Client.objects.create(
        workspace=workspace, name='C', email='c@del.com',
        public_code='CLI-DEL001',
    )


@pytest.fixture
def briefing(db, workspace, client):
    from apps.briefings.models import Briefing
    return Briefing.objects.create(
        workspace=workspace, client=client,
        title='B', structure_snapshot={'sections': []},
    )


def _get_callback(entry):
    """
    Extrai o callback de uma entrada de `run_on_commit`.

    Suporta múltiplos formatos do Django:
        - (sids, callback)              — Django < 6.x
        - (sids, robust, callback)      — Django 6.x+
    """
    for item in reversed(entry):
        if callable(item):
            return item
    raise TypeError(
        f'Nenhum callable encontrado em entrada de run_on_commit: {entry!r}'
    )


def _run_pending_on_commit():
    """
    Executa os callbacks de `transaction.on_commit` que estão
    pendentes na conexão atual. Isso simula o que o Django faria
    no commit real da transação.

    NÃO engole exceções. Se o callback falha, a exceção sobe —
    é exatamente o que queremos: o teste vê o erro real.
    """
    run_on_commit = getattr(connection, 'run_on_commit', None)
    if not run_on_commit:
        return
    pending = list(run_on_commit)
    run_on_commit.clear()
    for entry in pending:
        _get_callback(entry)()


@pytest.mark.django_db
class TestBriefingDeletion:

    def test_delete_schedules_on_commit(self, briefing):
        """
        Ao excluir o briefing, o receiver `pre_delete` agenda um
        callback via `transaction.on_commit`.
        """
        connection.run_on_commit.clear()

        briefing.delete()

        pending = list(connection.run_on_commit)
        assert len(pending) >= 1, (
            'Nenhum callback de on_commit foi agendado pelo pre_delete '
            'do Briefing.'
        )

    def test_callback_calls_ingest_service(self, briefing):
        """
        Executa os callbacks pendentes e valida que
        `IngestService.ingest_change_event` foi chamado com os
        argumentos corretos.

        Se o callback levantar exceção (ex.: import quebrado,
        argumento inválido), a exceção SOBE — o teste falha com o
        traceback do callback, não com um assert genérico.
        """
        briefing_id = briefing.id
        workspace_id = briefing.workspace_id
        client_id = briefing.client_id

        connection.run_on_commit.clear()

        with patch(
            'apps.intelligence.services.IngestService.ingest_change_event',
        ) as mock_ingest:
            briefing.delete()
            _run_pending_on_commit()

        assert mock_ingest.called, (
            'IngestService.ingest_change_event não foi chamado, mesmo '
            'sem exceção no callback. Verifique o corpo do `_ingest` '
            'em `apps/briefings/signals.py`.'
        )
        kw = mock_ingest.call_args.kwargs
        assert kw['workspace_id'] == workspace_id
        assert kw['client_id'] == client_id
        assert kw['briefing_id'] == briefing_id
        assert kw['source_kind'] == 'client.updated'
        assert 'briefing.deleted' in kw['source_ref']