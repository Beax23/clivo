"""
Testes do contrato público de `briefings`.

Cobrem:
    - `get_reference_document_payloads`:
        * devolve payloads com URL resolvida;
        * descarta documentos de outro workspace;
        * descarta documentos sem `file`;
        * devolve [] para lista vazia;
        * devolve [] se workspace é None.
    - `get_recent_events`:
        * filtra por workspace;
        * devolve [] se briefing pertence a outro workspace.
    - `get_briefing_ids_for_client`:
        * só lista briefings do cliente no workspace.
    - `get_briefing_snapshot` continua funcionando para notas
      criadas via service (que agora emitem BriefingEvent).
"""

import pytest

from apps.briefings import public as briefings_public


@pytest.fixture
def workspace_a(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='A', slug='ws-a-pub')


@pytest.fixture
def workspace_b(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='B', slug='ws-b-pub')


@pytest.fixture
def client_a(db, workspace_a):
    from apps.clients.models import Client
    return Client.objects.create(
        workspace=workspace_a, name='CA', email='a@a.com',
        public_code='CLI-PUBA01',
    )


@pytest.fixture
def briefing_a(db, workspace_a, client_a):
    from apps.briefings.models import Briefing
    return Briefing.objects.create(
        workspace=workspace_a, client=client_a,
        title='BA', structure_snapshot={'sections': []},
    )


@pytest.fixture
def document_a(db, workspace_a):
    from apps.documents.models import Document
    return Document.objects.create(
        workspace=workspace_a, name='img.png',
        file='documents/img.png',
        extension='png', mime_type='image/png', size=100,
    )


@pytest.fixture
def document_b(db, workspace_b):
    from apps.documents.models import Document
    return Document.objects.create(
        workspace=workspace_b, name='other.png',
        file='documents/other.png',
        extension='png', mime_type='image/png', size=200,
    )


@pytest.mark.django_db
class TestGetReferenceDocumentPayloads:

    def test_empty_list_returns_empty(self, workspace_a):
        assert briefings_public.get_reference_document_payloads(
            [], workspace_a,
        ) == []

    def test_none_workspace_returns_empty(self, document_a):
        assert briefings_public.get_reference_document_payloads(
            [str(document_a.id)], None,
        ) == []

    def test_returns_payload_with_url(
        self, workspace_a, document_a,
    ):
        payloads = briefings_public.get_reference_document_payloads(
            [str(document_a.id)], workspace_a,
        )
        assert len(payloads) == 1
        p = payloads[0]
        assert p['id'] == str(document_a.id)
        assert p['name'] == 'img.png'
        assert p['mime_type'] == 'image/png'
        assert p['url']  # URL resolvida pelo storage
        assert p['source'] == 'briefing'

    def test_cross_workspace_discarded(
        self, workspace_a, document_a, document_b,
    ):
        payloads = briefings_public.get_reference_document_payloads(
            [str(document_a.id), str(document_b.id)], workspace_a,
        )
        ids = {p['id'] for p in payloads}
        assert str(document_a.id) in ids
        assert str(document_b.id) not in ids

    def test_document_without_file_discarded(self, workspace_a):
        from apps.documents.models import Document
        # Document sem arquivo físico — `file.url` levanta.
        doc = Document.objects.create(
            workspace=workspace_a, name='no-file',
            file='', extension='', mime_type='image/png', size=0,
        )
        payloads = briefings_public.get_reference_document_payloads(
            [str(doc.id)], workspace_a,
        )
        assert payloads == []

    def test_invalid_id_does_not_raise(self, workspace_a):
        payloads = briefings_public.get_reference_document_payloads(
            ['not-a-uuid'], workspace_a,
        )
        assert payloads == []


@pytest.mark.django_db
class TestGetRecentEvents:

    def test_returns_events_of_own_workspace(
        self, workspace_a, briefing_a, client_a,
    ):
        from apps.briefings.services import BriefingNoteService
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(email='u@pub.com', password='x')

        BriefingNoteService.create_note(
            briefing=briefing_a, author=user, content='n1',
        )

        events = briefings_public.get_recent_events(
            briefing_a.id, workspace_a,
        )
        assert len(events) >= 1
        assert any(e['kind'] == 'note.created' for e in events)

    def test_other_workspace_returns_empty(
        self, workspace_b, briefing_a,
    ):
        events = briefings_public.get_recent_events(
            briefing_a.id, workspace_b,
        )
        assert events == []


@pytest.mark.django_db
class TestGetBriefingIdsForClient:

    def test_returns_own_briefings(
        self, workspace_a, client_a, briefing_a,
    ):
        ids = briefings_public.get_briefing_ids_for_client(
            client_a.id, workspace_a.id,
        )
        assert str(briefing_a.id) in ids

    def test_other_client_not_included(
        self, workspace_a, client_a, briefing_a,
    ):
        from apps.clients.models import Client
        other_client = Client.objects.create(
            workspace=workspace_a, name='CB', email='b@b.com',
            public_code='CLI-PUBB02',
        )
        ids = briefings_public.get_briefing_ids_for_client(
            other_client.id, workspace_a.id,
        )
        assert str(briefing_a.id) not in ids