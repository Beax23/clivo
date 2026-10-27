"""
Testes do encaminhamento de eventos de `clients` para o
`IngestService`.

Cobrem:
    - `client.updated` chega ao `IngestService` via `on_commit`.
    - `note.created/updated/deleted` chegam com o `source_kind`
      correto (NÃO briefing).
    - `pre_delete` de `Client` publica invalidação.

Não testa o `IngestService` em si — esse já tem seus testes em
`intelligence`. Aqui validamos a PONTE.

Usa `django_capture_on_commit_callbacks` (fixture do pytest-django
4.4+) para capturar os callbacks de `transaction.on_commit`.
"""

import pytest
from unittest.mock import patch


@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS', slug='ws-sig')


@pytest.fixture
def client_obj(db, workspace):
    from apps.clients.models import Client
    return Client.objects.create(
        workspace=workspace, name='Cli', email='c@sig.com',
        public_code='CLI-SIG001',
    )


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(email='u@sig.com', password='x')


@pytest.mark.django_db
class TestClientUpdatedIngest:

    def test_client_updated_publishes_on_commit(
        self, client_obj, user, django_capture_on_commit_callbacks,
    ):
        from apps.clients.services import ClientService

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            ClientService.update_client(
                client=client_obj, actor=user, name='Novo Nome',
            )

        assert len(callbacks) >= 1

        with patch(
            'apps.intelligence.services.IngestService.ingest_change_event',
        ) as mock_ingest:
            for cb in callbacks:
                cb()

        assert mock_ingest.called
        kw = mock_ingest.call_args.kwargs
        assert kw['source_kind'] == 'client.updated'
        assert kw['client_id'] == client_obj.id


@pytest.mark.django_db
class TestClientNoteIngest:

    def test_note_created_uses_client_note_kind(
        self, client_obj, user, django_capture_on_commit_callbacks,
    ):
        from apps.clients.services import NoteService

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            NoteService.create_note(
                client=client_obj, author=user, content='n1',
            )

        with patch(
            'apps.intelligence.services.IngestService.ingest_change_event',
        ) as mock_ingest:
            for cb in callbacks:
                cb()

        assert mock_ingest.called
        kw = mock_ingest.call_args.kwargs
        assert kw['source_kind'] == 'client.note.created'

    def test_note_updated_uses_client_note_kind(
        self, client_obj, user, django_capture_on_commit_callbacks,
    ):
        from apps.clients.services import NoteService

        note = NoteService.create_note(
            client=client_obj, author=user, content='v1',
        )

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            NoteService.update_note(
                note=note, actor=user, content='v2',
            )

        with patch(
            'apps.intelligence.services.IngestService.ingest_change_event',
        ) as mock_ingest:
            for cb in callbacks:
                cb()

        assert mock_ingest.called
        kw = mock_ingest.call_args.kwargs
        assert kw['source_kind'] == 'client.note.updated'
        assert kw['source_ref'] == str(note.id)

    def test_note_deleted_uses_client_note_kind(
        self, client_obj, user, django_capture_on_commit_callbacks,
    ):
        from apps.clients.services import NoteService

        note = NoteService.create_note(
            client=client_obj, author=user, content='x',
        )
        note_id = note.id

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            NoteService.delete_note(note=note)

        with patch(
            'apps.intelligence.services.IngestService.ingest_change_event',
        ) as mock_ingest:
            for cb in callbacks:
                cb()

        assert mock_ingest.called
        kw = mock_ingest.call_args.kwargs
        assert kw['source_kind'] == 'client.note.deleted'
        assert kw['source_ref'] == str(note_id)


@pytest.mark.django_db
class TestClientDeletionIngest:

    def test_delete_schedules_on_commit(
        self, client_obj, django_capture_on_commit_callbacks,
    ):
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            client_obj.delete()

        assert len(callbacks) >= 1

    def test_delete_publishes_invalidation(
        self, client_obj, django_capture_on_commit_callbacks,
    ):
        client_id = client_obj.id
        workspace_id = client_obj.workspace_id

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            client_obj.delete()

        with patch(
            'apps.intelligence.services.IngestService.ingest_change_event',
        ) as mock_ingest:
            for cb in callbacks:
                cb()

        assert mock_ingest.called
        kw = mock_ingest.call_args.kwargs
        assert kw['client_id'] == client_id
        assert kw['workspace_id'] == workspace_id
        assert kw['source_kind'] == 'client.updated'
        assert 'client.deleted' in kw['source_ref']