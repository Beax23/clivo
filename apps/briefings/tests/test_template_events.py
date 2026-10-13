"""
Testes do histórico estrutural (BriefingTemplateEvent).
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

    def test_publish_emits_event(self, user_owner):
        # Reaproveita o published_template — mas o publish já foi feito
        # na fixture. Aqui criamos um novo.
        pass  # ver test_publish_emits_event_below

    def test_publish_emits_event_below(
        self, draft_template, user_owner,
    ):
        BriefingTemplateService.add_section(
            template=draft_template, title='S', actor=user_owner,
        )
        BriefingTemplateService.publish_template(
            template=draft_template, actor=user_owner,
        )
        assert BriefingTemplateEvent.objects.filter(
            template=draft_template, kind='template_published',
        ).count() == 1

    def test_set_active_emits_event(
        self, published_template, user_owner,
    ):
        BriefingTemplateService.set_active(
            template=published_template, is_active=False,
            actor=user_owner,
        )
        assert BriefingTemplateEvent.objects.filter(
            template=published_template, kind='template_deactivated',
        ).count() == 1

        BriefingTemplateService.set_active(
            template=published_template, is_active=True,
            actor=user_owner,
        )
        assert BriefingTemplateEvent.objects.filter(
            template=published_template, kind='template_activated',
        ).count() == 1