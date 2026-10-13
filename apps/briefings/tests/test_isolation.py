"""
Testes de isolamento multi-tenant.

Cobrem o requisito "nenhum cliente/workspace acessa dados de outro".
"""

import pytest

from apps.briefings.models import (
    Briefing,
    BriefingTemplate,
    BriefingNote,
)


URL_TEMPLATES = '/api/briefing-templates/'
URL_BRIEFINGS = '/api/briefings/'


# =========================================================================
# TEMPLATE
# =========================================================================

@pytest.mark.django_db
class TestTemplateIsolation:

    def test_owner_lists_own_templates(
        self, owner_client, published_template,
    ):
        resp = owner_client.get(URL_TEMPLATES)
        assert resp.status_code == 200
        ids = {item['id'] for item in resp.data}
        assert str(published_template.id) in ids

    def test_other_does_not_see_owner_templates(
        self, other_client, published_template,
    ):
        resp = other_client.get(URL_TEMPLATES)
        assert resp.status_code == 200
        ids = {item['id'] for item in resp.data}
        assert str(published_template.id) not in ids

    def test_other_cannot_retrieve_owner_template(
        self, other_client, published_template,
    ):
        resp = other_client.get(f'{URL_TEMPLATES}{published_template.id}/')
        assert resp.status_code == 404

    def test_outsider_gets_400_or_403(
        self, outsider_client, published_template,
    ):
        resp = outsider_client.get(URL_TEMPLATES)
        assert resp.status_code in (400, 403)


# =========================================================================
# BRIEFING
# =========================================================================

@pytest.mark.django_db
class TestBriefingIsolation:

    def test_other_does_not_see_owner_briefing(
        self, other_client, briefing_a,
    ):
        resp = other_client.get(URL_BRIEFINGS)
        assert resp.status_code == 200
        ids = {item['id'] for item in resp.data}
        assert str(briefing_a.id) not in ids

    def test_other_cannot_retrieve_owner_briefing(
        self, other_client, briefing_a,
    ):
        resp = other_client.get(f'{URL_BRIEFINGS}{briefing_a.id}/')
        assert resp.status_code == 404


# =========================================================================
# NOTAS
# =========================================================================

@pytest.mark.django_db
class TestNoteIsolation:

    def test_other_cannot_list_notes_of_owner_briefing(
        self, other_client, briefing_a,
    ):
        resp = other_client.get(
            f'{URL_BRIEFINGS}{briefing_a.id}/notes/'
        )
        assert resp.status_code in (403, 404)

    def test_note_not_exposed_in_portal_serializer(
        self, briefing_a, portal_session_a, user_owner,
    ):
        from apps.briefings.api.serializers import PortalBriefingSerializer

        BriefingNote.objects.create(
            briefing=briefing_a,
            author=user_owner,
            content='Nota interna que o cliente não pode ver.',
        )

        payload = PortalBriefingSerializer().to_representation(briefing_a)

        # Serializa tudo para string e confirma que a nota não aparece
        serialized = str(payload)
        assert 'Nota interna' not in serialized
        assert 'notes' not in payload