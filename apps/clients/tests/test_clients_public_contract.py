"""
Testes do contrato público de `clients`.

Cobrem:
    - `get_client_snapshot`: continua estável.
    - `get_client_notes_snapshot`:
        * retorna notas do cliente no workspace;
        * descarta cross-workspace;
        * devolve [] para cliente inexistente.
    - `get_client_context_hash`:
        * muda quando o contexto muda;
        * não muda em save sem alterar `context`;
        * devolve '' para cliente inexistente.
"""

import pytest

from apps.clients import public as clients_public


@pytest.fixture
def workspace_a(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='A', slug='ws-cli-a')


@pytest.fixture
def workspace_b(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='B', slug='ws-cli-b')


@pytest.fixture
def client_a(db, workspace_a):
    from apps.clients.models import Client
    return Client.objects.create(
        workspace=workspace_a, name='CA', email='a@a.com',
        public_code='CLI-PUB001',
    )


@pytest.fixture
def client_b(db, workspace_b):
    from apps.clients.models import Client
    return Client.objects.create(
        workspace=workspace_b, name='CB', email='b@b.com',
        public_code='CLI-PUB002',
    )


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(email='u@pub.com', password='x')


@pytest.mark.django_db
class TestClientSnapshot:

    def test_snapshot_returns_data(self, client_a):
        snap = clients_public.get_client_snapshot(client_a.id)
        assert snap is not None
        assert snap['id'] == str(client_a.id)
        assert snap['name'] == 'CA'
        assert snap['workspace_id'] == str(client_a.workspace_id)

    def test_snapshot_returns_none_for_unknown(self):
        import uuid
        assert clients_public.get_client_snapshot(uuid.uuid4()) is None

    def test_snapshot_returns_none_for_invalid_uuid(self):
        assert clients_public.get_client_snapshot('not-uuid') is None


@pytest.mark.django_db
class TestClientNotesSnapshot:

    def test_returns_notes_of_own_workspace(
        self, client_a, user,
    ):
        from apps.clients.services import NoteService
        NoteService.create_note(
            client=client_a, author=user, content='n1',
        )
        notes = clients_public.get_client_notes_snapshot(
            client_a.id, client_a.workspace,
        )
        assert len(notes) == 1
        assert notes[0]['content'] == 'n1'
        assert notes[0]['author_email'] == 'u@pub.com'

    def test_other_workspace_returns_empty(
        self, client_a, workspace_b,
    ):
        notes = clients_public.get_client_notes_snapshot(
            client_a.id, workspace_b,
        )
        assert notes == []

    def test_unknown_client_returns_empty(self, workspace_a):
        import uuid
        notes = clients_public.get_client_notes_snapshot(
            uuid.uuid4(), workspace_a,
        )
        assert notes == []


@pytest.mark.django_db
class TestClientContextHash:

    def test_empty_context_returns_empty_string(self, client_a):
        assert clients_public.get_client_context_hash(client_a.id) == ''

    def test_context_changes_hash(self, client_a):
        client_a.context = {'a': 1}
        client_a.save(update_fields=['context'])
        h1 = clients_public.get_client_context_hash(client_a.id)

        client_a.context = {'a': 2}
        client_a.save(update_fields=['context'])
        h2 = clients_public.get_client_context_hash(client_a.id)

        assert h1
        assert h2
        assert h1 != h2

    def test_same_context_same_hash(self, client_a):
        client_a.context = {'a': 1, 'b': 2}
        client_a.save(update_fields=['context'])
        h1 = clients_public.get_client_context_hash(client_a.id)

        # Re-save com o mesmo conteúdo
        client_a.save(update_fields=['context'])
        h2 = clients_public.get_client_context_hash(client_a.id)

        assert h1 == h2

    def test_unknown_client_returns_empty_string(self):
        import uuid
        assert clients_public.get_client_context_hash(uuid.uuid4()) == ''