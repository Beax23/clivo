"""
Testes da emissão de BriefingEvent para notas.

Cobrem:
    - create_note emite note.created com user=<autor>.
    - update_note emite note.updated com user=<autor>.
    - delete_note emite note.deleted.
    - Os eventos chegam ao intelligence via signal (transaction.on_commit).

ESTRATÉGIA DO on_commit:
    NÃO usamos `django_capture_on_commit_callbacks(execute=False)`.
    Executamos manualmente os callbacks pendentes, acessando
    `connection.run_on_commit` diretamente.

IMPORTANTE:
    A execução NÃO engole exceções. Se o callback falha, o teste
    vê o traceback real do erro — não um assert confuso.

    O formato de cada entrada de `run_on_commit` varia entre versões
    do Django:
        - Django < 6.x: (sids, callback)
        - Django 6.x+:  (sids, robust, callback)
    Por isso extraímos o callback via `_get_callback`.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from apps.briefings.models import BriefingEvent
from apps.briefings.services import BriefingNoteService


User = get_user_model()


@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS', slug='ws-notes')


@pytest.fixture
def client(db, workspace):
    from apps.clients.models import Client
    return Client.objects.create(
        workspace=workspace, name='C', email='c@notes.com',
        public_code='CLI-NOTES1',
    )


@pytest.fixture
def briefing(db, workspace, client):
    from apps.briefings.models import Briefing
    return Briefing.objects.create(
        workspace=workspace, client=client,
        title='B', structure_snapshot={'sections': []},
    )


@pytest.fixture
def user(db):
    return User.objects.create_user(email='u@notes.com', password='x')


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


@pytest.mark.django_db
class TestNoteEvents:

    def test_create_note_emits_event(self, briefing, user):
        note = BriefingNoteService.create_note(
            briefing=briefing, author=user, content='primeira',
        )
        events = BriefingEvent.objects.filter(
            briefing=briefing, kind='note.created',
        )
        assert events.count() == 1
        ev = events.first()
        assert ev.user_id == user.id
        assert ev.content['note_id'] == str(note.id)

    def test_update_note_emits_event(self, briefing, user):
        note = BriefingNoteService.create_note(
            briefing=briefing, author=user, content='v1',
        )
        BriefingNoteService.update_note(
            note=note, author=user, content='v2',
        )
        events = BriefingEvent.objects.filter(
            briefing=briefing, kind='note.updated',
        )
        assert events.count() == 1
        assert events.first().content['note_id'] == str(note.id)

    def test_delete_note_emits_event(self, briefing, user):
        note = BriefingNoteService.create_note(
            briefing=briefing, author=user, content='x',
        )
        note_id = note.id
        BriefingNoteService.delete_note(note=note, actor=user)
        events = BriefingEvent.objects.filter(
            briefing=briefing, kind='note.deleted',
        )
        assert events.count() == 1
        assert events.first().content['note_id'] == str(note_id)

    def test_events_ingested_via_on_commit(self, briefing, user):
        """
        Verifica que o signal publica `IngestService` via on_commit.

        Executa os callbacks pendentes manualmente. Se o callback
        falha, a exceção SOBE — o teste vê o traceback real.
        """
        from unittest.mock import patch

        connection.run_on_commit.clear()

        with patch(
            'apps.intelligence.services.IngestService.ingest_change_event',
        ) as mock_ingest:
            BriefingNoteService.create_note(
                briefing=briefing, author=user, content='trigger',
            )

            pending = list(connection.run_on_commit)
            connection.run_on_commit.clear()
            for entry in pending:
                _get_callback(entry)()

        assert mock_ingest.called, (
            'IngestService.ingest_change_event não foi chamado, mesmo '
            'sem exceção no callback. Verifique o corpo do `_ingest` '
            'em `apps/briefings/signals.py`.'
        )
        kw = mock_ingest.call_args.kwargs
        assert kw['source_kind'] == 'briefing.note.created'
        assert kw['client_id'] == briefing.client_id
        assert kw['briefing_id'] == briefing.id