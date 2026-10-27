"""
Testes de versionamento (Bloco 2 — P1).

Cobrem:
    - Criar rascunho clonando versão publicada
    - Criar rascunho em branco
    - Publicar versão arquiva a anterior
    - Nova versão NÃO afeta execuções antigas
    - Diff identifica mudanças reais
    - Diff respeita isolamento por workspace

RESTAURAÇÃO (restore_into_template):
    - Substitui a estrutura do modelo pela da versão escolhida
    - Despublica automaticamente um template `published`
    - Bloqueia se versão é de outro template
    - Aborta se estrutura é inválida (sem alterar nada)
    - Ignora documentos inexistentes/de outro workspace
    - Contabiliza referências ignoradas no evento
    - Cria nova versão draft refletindo o estado
    - Preserva briefings em execução
    - Grava evento de auditoria
"""

import pytest

from apps.briefings.models import (
    Briefing,
    BriefingTemplate,
    BriefingSection,
    BriefingQuestion,
    BriefingTemplateVersion,
    BriefingTemplateEvent,
)
from apps.briefings.services import (
    BriefingTemplateService,
    BriefingTemplateVersionService,
)
from apps.briefings.exceptions import BriefingError


# =========================================================================
# CRIAÇÃO
# =========================================================================

@pytest.mark.django_db
class TestCreateVersion:

    def test_create_draft_clone_current(
        self, published_template, user_owner,
    ):
        current = (
            BriefingTemplateVersionService.get_current_published(
                published_template,
            )
        )
        assert current is not None

        new_version = (
            BriefingTemplateVersionService.create_draft_from_template(
                template=published_template,
                actor=user_owner,
                blank=False,
            )
        )
        assert new_version.status == 'draft'
        assert new_version.version_number == current.version_number + 1
        assert new_version.structure.get('sections')
        assert len(new_version.structure['sections']) == 2

    def test_create_draft_blank(
        self, published_template, user_owner,
    ):
        new_version = (
            BriefingTemplateVersionService.create_draft_from_template(
                template=published_template,
                actor=user_owner,
                blank=True,
            )
        )
        assert new_version.status == 'draft'
        assert new_version.structure.get('sections') == []


# =========================================================================
# PUBLICAÇÃO
# =========================================================================

@pytest.mark.django_db
class TestPublishVersion:

    def test_publish_archives_previous(
        self, published_template, user_owner,
    ):
        previous = (
            BriefingTemplateVersionService.get_current_published(
                published_template,
            )
        )

        new_version = (
            BriefingTemplateVersionService.create_draft_from_template(
                template=published_template,
                actor=user_owner,
            )
        )
        BriefingTemplateVersionService.publish(
            version=new_version, actor=user_owner,
        )

        previous.refresh_from_db()
        assert previous.status == 'archived'
        assert new_version.status == 'published'

        current = (
            BriefingTemplateVersionService.get_current_published(
                published_template,
            )
        )
        assert current.id == new_version.id

    def test_publish_requires_structure(
        self, published_template, user_owner,
    ):
        new_version = (
            BriefingTemplateVersionService.create_draft_from_template(
                template=published_template,
                actor=user_owner,
                blank=True,
            )
        )
        with pytest.raises(BriefingError):
            BriefingTemplateVersionService.publish(
                version=new_version, actor=user_owner,
            )


# =========================================================================
# PRESERVAÇÃO
# =========================================================================

@pytest.mark.django_db
class TestVersionPreservesExecutions:

    def test_new_version_does_not_change_existing_execution(
        self, briefing_a, published_template, user_owner,
    ):
        old_snapshot = dict(briefing_a.structure_snapshot)
        old_version_id = str(briefing_a.template_version_id)

        new_version = (
            BriefingTemplateVersionService.create_draft_from_template(
                template=published_template,
                actor=user_owner,
            )
        )
        BriefingTemplateVersionService.publish(
            version=new_version, actor=user_owner,
        )

        briefing_a.refresh_from_db()
        assert briefing_a.structure_snapshot == old_snapshot
        assert str(briefing_a.template_version_id) == old_version_id

    def test_new_version_used_by_new_executions(
        self, briefing_a, published_template, client_a,
        workspace_a, user_owner,
    ):
        from apps.briefings.services import BriefingService

        new_version = (
            BriefingTemplateVersionService.create_draft_from_template(
                template=published_template,
                actor=user_owner,
            )
        )
        BriefingTemplateVersionService.publish(
            version=new_version, actor=user_owner,
        )

        new_briefing = BriefingService.create_briefing(
            template=published_template,
            client=client_a,
            workspace=workspace_a,
            actor=user_owner,
        )
        assert new_briefing.template_version_id == new_version.id
        assert briefing_a.template_version_id != new_version.id


# =========================================================================
# DIFF
# =========================================================================

@pytest.mark.django_db
class TestDiff:

    def test_diff_no_changes(
        self, published_template, user_owner,
    ):
        data = BriefingTemplateVersionService.diff_against_published(
            published_template,
        )
        assert data['has_baseline'] is True
        assert data['summary']['total_changes'] == 0

    def test_diff_detects_added_question(
        self, published_template, user_owner,
    ):
        section = published_template.sections.first()
        BriefingQuestion.objects.create(
            section=section,
            text='Nova pergunta adicionada',
            position=99,
            is_required=True,
            allowed_response_formats=['text'],
        )

        data = BriefingTemplateVersionService.diff_against_published(
            published_template,
        )
        assert data['summary']['questions_added'] == 1
        added = data['questions']['added'][0]
        assert added['text'] == 'Nova pergunta adicionada'

    def test_diff_detects_changed_question(
        self, published_template, user_owner,
    ):
        q = published_template.sections.first().questions.first()
        q.text = 'Texto completamente diferente'
        q.save(update_fields=['text'])

        data = BriefingTemplateVersionService.diff_against_published(
            published_template,
        )
        assert data['summary']['questions_changed'] >= 1
        changed_ids = {c['id'] for c in data['questions']['changed']}
        assert str(q.id) in changed_ids

    def test_diff_no_baseline(self, draft_template, user_owner):
        data = BriefingTemplateVersionService.diff_against_published(
            draft_template,
        )
        assert data['has_baseline'] is False
        assert data['base_version'] is None


# =========================================================================
# RESTAURAÇÃO — substitui estrutura do modelo
# =========================================================================

def _make_draft_with_two_sections(template, workspace, actor):
    """
    Zera a estrutura atual e recria 2 seções com 1 pergunta cada.
    Retorna a nova versão em rascunho gerada.
    """
    BriefingSection.objects.filter(template=template).delete()

    s1 = BriefingSection.objects.create(
        template=template, title='Alpha', position=1,
    )
    BriefingQuestion.objects.create(
        section=s1, text='Pergunta A1', position=1,
        is_required=True, allowed_response_formats=['text'],
    )
    BriefingQuestion.objects.create(
        section=s1, text='Pergunta A2', position=2,
        is_required=False, allowed_response_formats=['text'],
    )

    s2 = BriefingSection.objects.create(
        template=template, title='Beta', position=2,
    )
    BriefingQuestion.objects.create(
        section=s2, text='Pergunta B1', position=1,
        is_required=True, allowed_response_formats=['text'],
    )

    return BriefingTemplateVersionService.create_draft_from_template(
        template=template, actor=actor,
    )


@pytest.mark.django_db
class TestRestoreInto:

    def test_restore_replaces_structure(
        self, draft_template, user_owner,
    ):
        # Prepara uma versão com estrutura conhecida
        source = _make_draft_with_two_sections(
            draft_template, draft_template.workspace, user_owner,
        )

        # Agora mexe na estrutura atual para ficar diferente
        BriefingSection.objects.filter(template=draft_template).delete()
        s_extra = BriefingSection.objects.create(
            template=draft_template, title='Extra', position=1,
        )
        BriefingQuestion.objects.create(
            section=s_extra, text='Pergunta Extra 1', position=1,
            is_required=True, allowed_response_formats=['text'],
        )
        assert draft_template.sections.count() == 1

        # Restaura a v anterior
        new_version = (
            BriefingTemplateVersionService.restore_into_template(
                template=draft_template,
                source_version=source,
                actor=user_owner,
            )
        )

        # 1) Nova versão em draft refletindo a estrutura restaurada
        assert new_version.status == 'draft'
        assert new_version.template_id == draft_template.id
        assert len(new_version.structure['sections']) == 2

        # 2) Tabelas do template refletem a estrutura restaurada
        draft_template.refresh_from_db()
        sections = list(
            draft_template.sections
            .order_by('position')
            .prefetch_related('questions')
        )
        assert len(sections) == 2
        assert sections[0].title == 'Alpha'
        assert sections[1].title == 'Beta'
        assert sections[0].questions.count() == 2
        assert sections[1].questions.count() == 1

    def test_restore_auto_unpublishes_when_published(
        self, published_template, user_owner,
    ):
        """
        Contrato atual: `restore_into_template` DESPUBLICA
        automaticamente um template `published` antes de substituir
        a estrutura. Este é o comportamento aprovado no modal do
        frontend. O teste valida que o template termina em `draft`
        e a estrutura é substituída.
        """
        current = (
            BriefingTemplateVersionService.get_current_published(
                published_template,
            )
        )
        assert current is not None

        new_version = (
            BriefingTemplateVersionService.restore_into_template(
                template=published_template,
                source_version=current,
                actor=user_owner,
            )
        )

        # Template foi despublicado automaticamente.
        published_template.refresh_from_db()
        assert published_template.status == 'draft'

        # Nova versão em rascunho foi criada.
        assert new_version.status == 'draft'
        assert new_version.template_id == published_template.id

    def test_restore_wrong_template(
        self, draft_template, workspace_b, user_owner, user_other,
    ):
        # Cria um template "estranho" no outro workspace
        other_template = BriefingTemplate.objects.create(
            workspace=workspace_b,
            name='Outro',
            status=BriefingTemplate.STATUS_DRAFT,
            created_by=user_other,
        )
        other_version = (
            BriefingTemplateVersionService.create_draft_from_template(
                template=other_template, actor=user_other, blank=True,
            )
        )

        with pytest.raises(BriefingError):
            BriefingTemplateVersionService.restore_into_template(
                template=draft_template,
                source_version=other_version,
                actor=user_owner,
            )

    def test_restore_invalid_structure_aborts(
        self, draft_template, user_owner,
    ):
        # Cria uma versão "válida" primeiro
        version = (
            BriefingTemplateVersionService.create_draft_from_template(
                template=draft_template, actor=user_owner,
            )
        )
        # Envenena a estrutura — pergunta sem texto
        version.structure = {
            'snapshot_version': 1,
            'template_name': draft_template.name,
            'sections': [
                {
                    'id': 's1',
                    'title': 'Quebrada',
                    'description': '',
                    'position': 1,
                    'questions': [
                        {'id': 'q1', 'text': '', 'question_type': 'text'},
                    ],
                },
            ],
        }
        version.save(update_fields=['structure'])

        # Estado antes
        sections_before = list(
            draft_template.sections.values_list('id', flat=True)
        )

        with pytest.raises(BriefingError):
            BriefingTemplateVersionService.restore_into_template(
                template=draft_template,
                source_version=version,
                actor=user_owner,
            )

        # Nada mudou
        sections_after = list(
            draft_template.sections.values_list('id', flat=True)
        )
        assert sections_before == sections_after

    def test_restore_ignores_missing_documents(
        self, draft_template, user_owner, workspace_a,
    ):
        """
        Referência a document inexistente não bloqueia.
        É ignorada e contabilizada.
        """
        import uuid

        bogus_doc_id = str(uuid.uuid4())

        version = (
            BriefingTemplateVersionService.create_draft_from_template(
                template=draft_template, actor=user_owner,
            )
        )
        version.structure = {
            'snapshot_version': 1,
            'template_name': draft_template.name,
            'sections': [
                {
                    'id': 's1',
                    'title': 'Com ref quebrada',
                    'description': '',
                    'position': 1,
                    'questions': [
                        {
                            'id': 'q1',
                            'text': 'Pergunta com ref',
                            'question_type': 'text',
                            'allowed_response_formats': ['text'],
                            'is_required': True,
                            'reference_document_ids': [bogus_doc_id],
                        },
                    ],
                },
            ],
        }
        version.save(update_fields=['structure'])

        new_version = (
            BriefingTemplateVersionService.restore_into_template(
                template=draft_template,
                source_version=version,
                actor=user_owner,
            )
        )
        assert new_version.status == 'draft'

        # A pergunta existe, sem referências
        q = BriefingQuestion.objects.get(
            section__template=draft_template,
            text='Pergunta com ref',
        )
        assert q.reference_documents.count() == 0

        # Evento de auditoria registra a referência ignorada
        event = (
            BriefingTemplateEvent.objects
            .filter(
                template=draft_template,
                kind=BriefingTemplateEvent.KIND_TEMPLATE_UPDATED,
                content__action='restore_from_version',
            )
            .order_by('-created_at')
            .first()
        )
        assert event is not None
        assert event.content['ignored_references_count'] == 1

    def test_restore_does_not_touch_existing_briefings(
        self, published_template, user_owner, workspace_a, client_a,
    ):
        """
        Briefings criados a partir do modelo continuam com o snapshot
        original, mesmo depois de restaurarmos.
        """
        from apps.briefings.services import BriefingService

        # Cria um briefing a partir do published_template
        briefing = BriefingService.create_briefing(
            template=published_template,
            client=client_a,
            workspace=workspace_a,
            actor=user_owner,
        )
        snapshot_before = dict(briefing.structure_snapshot)

        # Agora despublique e restaure para uma estrutura diferente
        BriefingTemplateService.unpublish_template(
            template=published_template, actor=user_owner,
        )
        published_template.refresh_from_db()

        current = (
            BriefingTemplateVersionService.get_current_published(
                published_template,
            )
        )
        assert current is not None

        BriefingTemplateVersionService.restore_into_template(
            template=published_template,
            source_version=current,
            actor=user_owner,
        )

        briefing.refresh_from_db()
        assert briefing.structure_snapshot == snapshot_before

    def test_restore_logs_event(
        self, draft_template, user_owner,
    ):
        source = _make_draft_with_two_sections(
            draft_template, draft_template.workspace, user_owner,
        )

        # Limpa
        BriefingSection.objects.filter(template=draft_template).delete()

        BriefingTemplateVersionService.restore_into_template(
            template=draft_template,
            source_version=source,
            actor=user_owner,
        )

        event = (
            BriefingTemplateEvent.objects
            .filter(
                template=draft_template,
                kind=BriefingTemplateEvent.KIND_TEMPLATE_UPDATED,
                content__action='restore_from_version',
            )
            .order_by('-created_at')
            .first()
        )
        assert event is not None
        assert event.user_id == user_owner.id
        assert (
            event.content['source_version_id'] == str(source.id)
        )
        assert event.content['sections_created'] == 2
        assert event.content['questions_created'] == 3