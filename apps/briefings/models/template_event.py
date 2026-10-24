"""
Modelo BriefingTemplateEvent — histórico estrutural do template.

REGRA ARQUITETURAL
------------------
Histórico APPEND-ONLY das alterações estruturais feitas em
templates, sessões e perguntas.

Cobre a pergunta "quem apagou a pergunta 7 do template X em 12/10?".

Diferente de BriefingEvent (que vive no runtime do briefing), este
modelo registra a evolução do TEMPLATE. Não é vinculado a execuções.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class BriefingTemplateEvent(models.Model):

    KIND_TEMPLATE_CREATED = 'template_created'
    KIND_TEMPLATE_UPDATED = 'template_updated'
    KIND_TEMPLATE_PUBLISHED = 'template_published'
    KIND_TEMPLATE_UNPUBLISHED = 'template_unpublished'
    KIND_SECTION_CREATED = 'section_created'
    KIND_SECTION_UPDATED = 'section_updated'
    KIND_SECTION_DELETED = 'section_deleted'
    KIND_SECTION_REORDERED = 'section_reordered'
    KIND_QUESTION_CREATED = 'question_created'
    KIND_QUESTION_UPDATED = 'question_updated'
    KIND_QUESTION_DELETED = 'question_deleted'
    KIND_QUESTION_REORDERED = 'question_reordered'

    KIND_CHOICES = [
        (KIND_TEMPLATE_CREATED, 'Template criado'),
        (KIND_TEMPLATE_UPDATED, 'Template editado'),
        (KIND_TEMPLATE_PUBLISHED, 'Template publicado'),
        (KIND_TEMPLATE_UNPUBLISHED, 'Template voltou para rascunho'),
        (KIND_SECTION_CREATED, 'Sessão criada'),
        (KIND_SECTION_UPDATED, 'Sessão editada'),
        (KIND_SECTION_DELETED, 'Sessão removida'),
        (KIND_SECTION_REORDERED, 'Sessões reordenadas'),
        (KIND_QUESTION_CREATED, 'Pergunta criada'),
        (KIND_QUESTION_UPDATED, 'Pergunta editada'),
        (KIND_QUESTION_DELETED, 'Pergunta removida'),
        (KIND_QUESTION_REORDERED, 'Perguntas reordenadas'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    template = models.ForeignKey(
        'briefings.BriefingTemplate',
        on_delete=models.CASCADE,
        related_name='events',
    )

    kind = models.CharField(
        max_length=40,
        choices=KIND_CHOICES,
        db_index=True,
    )

    section_id = models.UUIDField(null=True, blank=True, db_index=True)

    question_id = models.UUIDField(null=True, blank=True, db_index=True)

    content = models.JSONField(
        default=dict,
        blank=True,
        help_text=_('Detalhes específicos do tipo de evento'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='briefing_template_events',
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'briefing_template_event'
        verbose_name = _('Evento de Template de Briefing')
        verbose_name_plural = _('Eventos de Template de Briefing')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['template', '-created_at']),
            models.Index(fields=['template', 'kind', '-created_at']),
        ]

    def __str__(self):
        return f"{self.template_id} · {self.kind}"