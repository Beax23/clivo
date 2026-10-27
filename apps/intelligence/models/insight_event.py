"""
Modelo InsightEvent — registra mudanças relevantes nas fontes.

IDEMPOTÊNCIA
------------
A `dedupe_key` representa a IDENTIDADE ÚNICA da ocorrência do evento,
não apenas a origem. Ela é composta por:

    workspace + client + briefing + source_kind + source_ref + occurrence_id

`occurrence_id` é um identificador único gerado pelo módulo de origem
para cada fato atômico (ex: o UUID do BriefingEvent, o UUID da nota
de briefing, o UUID da ClientNote + updated_at, ou um `updated_at`
monotônico). Isso impede que a mesma nota atualizada duas vezes seja
silenciosamente ignorada como "duplicada para sempre".

PERGUNTAS COMPLEMENTARES
------------------------
Eventos originados pelo bloco complementar de um briefing usam
`SOURCE_KIND_BRIEFING_SUPPLEMENTARY_*`. Distintos dos eventos do
bloco original, para que a inteligência possa rastrear a evolução
do conhecimento do cliente separadamente.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class InsightEvent(models.Model):

    SOURCE_KIND_BRIEFING_ANSWER = 'briefing.answer.submitted'
    SOURCE_KIND_BRIEFING_NOTE_CREATED = 'briefing.note.created'
    SOURCE_KIND_BRIEFING_NOTE_UPDATED = 'briefing.note.updated'
    SOURCE_KIND_BRIEFING_NOTE_DELETED = 'briefing.note.deleted'
    SOURCE_KIND_BRIEFING_SUPPLEMENTARY_QUESTION_ADDED = (
        'briefing.supplementary.question_added'
    )
    SOURCE_KIND_BRIEFING_SUPPLEMENTARY_QUESTION_REMOVED = (
        'briefing.supplementary.question_removed'
    )
    SOURCE_KIND_BRIEFING_SUPPLEMENTARY_COMPLETED = (
        'briefing.supplementary.completed'
    )
    SOURCE_KIND_CLIENT_NOTE_CREATED = 'client.note.created'
    SOURCE_KIND_CLIENT_NOTE_UPDATED = 'client.note.updated'
    SOURCE_KIND_CLIENT_NOTE_DELETED = 'client.note.deleted'
    SOURCE_KIND_CLIENT_UPDATED = 'client.updated'
    SOURCE_KIND_CLIENT_CONTEXT_UPDATED = 'client.context.updated'

    SOURCE_KIND_CHOICES = [
        (SOURCE_KIND_BRIEFING_ANSWER, 'Resposta de briefing enviada'),
        (SOURCE_KIND_BRIEFING_NOTE_CREATED, 'Nota de briefing criada'),
        (SOURCE_KIND_BRIEFING_NOTE_UPDATED, 'Nota de briefing atualizada'),
        (SOURCE_KIND_BRIEFING_NOTE_DELETED, 'Nota de briefing excluída'),
        (
            SOURCE_KIND_BRIEFING_SUPPLEMENTARY_QUESTION_ADDED,
            'Pergunta complementar adicionada',
        ),
        (
            SOURCE_KIND_BRIEFING_SUPPLEMENTARY_QUESTION_REMOVED,
            'Pergunta complementar removida',
        ),
        (
            SOURCE_KIND_BRIEFING_SUPPLEMENTARY_COMPLETED,
            'Perguntas complementares concluídas',
        ),
        (SOURCE_KIND_CLIENT_NOTE_CREATED, 'Nota de cliente criada'),
        (SOURCE_KIND_CLIENT_NOTE_UPDATED, 'Nota de cliente atualizada'),
        (SOURCE_KIND_CLIENT_NOTE_DELETED, 'Nota de cliente excluída'),
        (SOURCE_KIND_CLIENT_UPDATED, 'Cliente atualizado'),
        (SOURCE_KIND_CLIENT_CONTEXT_UPDATED, 'Contexto do cliente atualizado'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    workspace = models.ForeignKey(
        'workspaces.Workspace', on_delete=models.CASCADE,
        related_name='insight_events', db_index=True,
    )
    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE,
        related_name='insight_events', db_index=True,
    )
    briefing = models.ForeignKey(
        'briefings.Briefing', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='insight_events',
    )

    source_kind = models.CharField(
        max_length=50, choices=SOURCE_KIND_CHOICES, db_index=True,
    )

    source_ref = models.CharField(
        max_length=255, blank=True, db_index=True,
        help_text=_("Referência ao objeto de origem (ex: question_id, note_id)."),
    )

    occurrence_id = models.CharField(
        max_length=255,
        help_text=_(
            "Identificador único da ocorrência atômica. Ex: UUID do "
            "BriefingEvent, UUID da nota + hash do conteúdo, ou timestamp "
            "monotônico. Impede que atualizações legítimas sejam "
            "confundidas com reentrância."
        ),
    )

    dedupe_key = models.CharField(max_length=512, unique=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'intelligence_insight_event'
        verbose_name = _('Evento de Insight')
        verbose_name_plural = _('Eventos de Insight')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'created_at']),
            models.Index(fields=['client', 'created_at']),
            models.Index(fields=['briefing', 'created_at']),
            models.Index(fields=['source_kind', 'created_at']),
        ]

    def __str__(self):
        return f"{self.source_kind} @ {self.client} ({self.created_at:%Y-%m-%d %H:%M})"

    def save(self, *args, **kwargs):
        if not self.dedupe_key:
            parts = [
                str(self.workspace_id),
                str(self.client_id),
                str(self.briefing_id or ''),
                self.source_kind,
                self.source_ref or '',
                self.occurrence_id,
            ]
            self.dedupe_key = ':'.join(parts)
        super().save(*args, **kwargs)