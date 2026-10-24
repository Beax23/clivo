"""
Testes do histórico estrutural (BriefingTemplateEvent).

NOTA: os testes de `set_active` foram removidos porque o conceito
de `is_active` foi extinto — o estado do template agora é único e
vive em `status` (draft / published / archived).
"""

import pytest

from apps.briefings.models import (
    BriefingTemplate,
    BriefingTemplateEvent,
)
from apps.briefings.services import BriefingTemplateService


@pytest.mark.django_db
class TestTemplateEvents:

    def test_create_template_emits_event(self, workspace_a, user_owner):
        tpl = BriefingTemplateService.create_template(
            workspace=workspace_a,
            name='Novo Template',
            actor=user_owner,
        )
        events = BriefingTemplateEvent.objects.filter(template=tpl)
        assert events.count() == 1
        assert events.first().kind == 'template_created'

    def test_add_section_emits_event(
        self, draft_template, user_owner,
    ):
        BriefingTemplateService.add_section(
            template=draft_template,
            title='Sessão 1',
            actor=user_owner,
        )
        assert BriefingTemplateEvent.objects.filter(
            template=draft_template, kind='section_created',
        ).count() == 1

    def test_add_question_emits_event(
        self, draft_template, user_owner,
    ):
        section = BriefingTemplateService.add_section(
            template=draft_template, title='S', actor=user_owner,
        )
        BriefingTemplateService.add_question(
            section=section, text='Pergunta?', actor=user_owner,
        )
        assert BriefingTemplateEvent.objects.filter(
            template=draft_template, kind='question_created',
        ).count() == 1

    def test_delete_question_emits_event(
        self, draft_template, user_owner,
    ):
        from apps.briefings.models import BriefingQuestion
        section = BriefingTemplateService.add_section(
            template=draft_template, title='S', actor=user_owner,
        )
        q = BriefingTemplateService.add_question(
            section=section, text='Pergunta?', actor=user_owner,
        )
        BriefingTemplateService.delete_question(
            question=q, actor=user_owner,
        )
        assert BriefingTemplateEvent.objects.filter(
            template=draft_template, kind='question_deleted',
        ).count() == 1

    def test_publish_emits_event(self, draft_template, user_owner):
        BriefingTemplateService.add_section(
            template=draft_template, title='S', actor=user_owner,
        )
        BriefingTemplateService.publish_template(
            template=draft_template, actor=user_owner,
        )
        assert BriefingTemplateEvent.objects.filter(
            template=draft_template, kind='template_published',
        ).count() == 1