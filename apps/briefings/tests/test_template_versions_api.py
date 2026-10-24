"""
Testes da API de versões de template.

Cobrem o contrato do Bloco de Versionamento + carregamento sob demanda:

    1. GET /versions/ retorna metadados SEM `structure`
    2. GET /versions/{id}/ retorna o detalhe COM `structure`
    3. Autorização: view vs manage
    4. Isolamento por workspace
    5. Versão inexistente → 404
    6. Excluir versão publicada → 400/409 (bloqueado)
    7. Excluir versão draft/archived → 204
"""

import pytest

from apps.briefings.models import BriefingTemplateVersion
from apps.briefings.services import BriefingTemplateVersionService


URL_LIST = '/api/briefing-templates/{tid}/versions/'
URL_DETAIL = '/api/briefing-templates/{tid}/versions/{vid}/'


# =========================================================================
# HELPERS
# =========================================================================

def _ensure_published_version(template, actor):
    """
    Garante que o template tem uma versão publicada.
    Retorna a versão.
    """
    current = BriefingTemplateVersionService.get_current_published(template)
    if current is not None:
        return current
    draft = BriefingTemplateVersionService.create_draft_from_template(
        template=template, actor=actor,
    )
    BriefingTemplateVersionService.publish(version=draft, actor=actor)
    return draft


# =========================================================================
# LISTAGEM — metadados apenas
# =========================================================================

@pytest.mark.django_db
class TestVersionsList:

    def test_list_returns_metadata_without_structure(
        self, owner_client, published_template, user_owner,
    ):
        _ensure_published_version(published_template, user_owner)

        url = URL_LIST.format(tid=published_template.id)
        resp = owner_client.get(url)
        assert resp.status_code == 200
        assert isinstance(resp.data, list)
        assert len(resp.data) >= 1

        first = resp.data[0]
        # Chaves esperadas no list
        assert 'id' in first
        assert 'version_number' in first
        assert 'status' in first
        assert 'sections_count' in first
        assert 'questions_count' in first
        assert 'published_at' in first
        assert 'created_at' in first
        # CRÍTICO: não deve conter structure
        assert 'structure' not in first

    def test_list_only_own_workspace(
        self, other_client, published_template, user_owner,
    ):
        _ensure_published_version(published_template, user_owner)
        url = URL_LIST.format(tid=published_template.id)
        resp = other_client.get(url)
        # Template não pertence ao workspace → 404
        assert resp.status_code == 404

    def test_list_unauthorized_user_gets_403_or_400(
        self, outsider_client, published_template, user_owner,
    ):
        _ensure_published_version(published_template, user_owner)
        url = URL_LIST.format(tid=published_template.id)
        resp = outsider_client.get(url)
        assert resp.status_code in (400, 403)


# =========================================================================
# DETALHE — com structure
# =========================================================================

@pytest.mark.django_db
class TestVersionDetail:

    def test_detail_returns_full_structure(
        self, owner_client, published_template, user_owner,
    ):
        version = _ensure_published_version(published_template, user_owner)

        url = URL_DETAIL.format(
            tid=published_template.id, vid=version.id,
        )
        resp = owner_client.get(url)
        assert resp.status_code == 200

        # Detalhe inclui structure completa
        assert 'structure' in resp.data
        structure = resp.data['structure']
        assert isinstance(structure, dict)
        assert 'sections' in structure
        assert len(structure['sections']) == 2  # fixture tem 2 sessões

        # Cada sessão tem questions
        for sec in structure['sections']:
            assert 'questions' in sec

    def test_detail_404_for_unknown_version(
        self, owner_client, published_template,
    ):
        import uuid
        url = URL_DETAIL.format(
            tid=published_template.id, vid=uuid.uuid4(),
        )
        resp = owner_client.get(url)
        assert resp.status_code == 404

    def test_detail_404_for_other_workspace(
        self, other_client, published_template, user_owner,
    ):
        version = _ensure_published_version(published_template, user_owner)
        url = URL_DETAIL.format(
            tid=published_template.id, vid=version.id,
        )
        resp = other_client.get(url)
        assert resp.status_code == 404

    def test_detail_unauthorized_user_gets_403_or_400(
        self, outsider_client, published_template, user_owner,
    ):
        version = _ensure_published_version(published_template, user_owner)
        url = URL_DETAIL.format(
            tid=published_template.id, vid=version.id,
        )
        resp = outsider_client.get(url)
        assert resp.status_code in (400, 403)


# =========================================================================
# DELETE
# =========================================================================

@pytest.mark.django_db
class TestVersionDelete:

    def test_cannot_delete_published_version(
        self, owner_client, published_template, user_owner,
    ):
        version = _ensure_published_version(published_template, user_owner)
        assert version.status == BriefingTemplateVersion.STATUS_PUBLISHED

        url = URL_DETAIL.format(
            tid=published_template.id, vid=version.id,
        )
        resp = owner_client.delete(url)
        # Bloqueado pelo service (400)
        assert resp.status_code in (400, 409)

        # A versão continua existindo
        assert BriefingTemplateVersion.objects.filter(id=version.id).exists()

    def test_can_delete_draft_version(
        self, owner_client, published_template, user_owner,
    ):
        # Cria uma draft extra
        draft = BriefingTemplateVersionService.create_draft_from_template(
            template=published_template, actor=user_owner,
        )
        assert draft.status == BriefingTemplateVersion.STATUS_DRAFT

        url = URL_DETAIL.format(
            tid=published_template.id, vid=draft.id,
        )
        resp = owner_client.delete(url)
        assert resp.status_code == 204

        assert not BriefingTemplateVersion.objects.filter(id=draft.id).exists()

    def test_delete_404_for_other_workspace(
        self, other_client, published_template, user_owner,
    ):
        draft = BriefingTemplateVersionService.create_draft_from_template(
            template=published_template, actor=user_owner,
        )
        url = URL_DETAIL.format(
            tid=published_template.id, vid=draft.id,
        )
        resp = other_client.delete(url)
        assert resp.status_code == 404

        # Não foi excluída
        assert BriefingTemplateVersion.objects.filter(id=draft.id).exists()


# =========================================================================
# ISOLAMENTO DE CACHE
# =========================================================================

@pytest.mark.django_db
class TestVersionSemantics:
    """
    Garantias de semântica que o frontend depende:

    - draft pode ser alterada
    - published é imutável (após publicação, sua estrutura não muda)
    """

    def test_published_version_does_not_change_after_new_draft(
        self, published_template, user_owner,
    ):
        version_v1 = _ensure_published_version(published_template, user_owner)
        v1_structure = dict(version_v1.structure)

        # Cria uma nova versão draft — não deve alterar v1
        BriefingTemplateVersionService.create_draft_from_template(
            template=published_template, actor=user_owner,
        )

        version_v1.refresh_from_db()
        assert version_v1.structure == v1_structure
        assert version_v1.status == BriefingTemplateVersion.STATUS_PUBLISHED