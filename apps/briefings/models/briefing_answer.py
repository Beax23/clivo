"""
Modelo BriefingAnswer — projeção do estado atual de uma pergunta.

REGRA ARQUITETURAL
------------------
BriefingAnswer NÃO substitui o histórico. Ele é uma VIEW do estado
atual, mantida em sincronia com os eventos.

Toda pergunta respondida tem UM e apenas UM BriefingAnswer. Novas
respostas atualizam o registro (apontando para o novo evento), mas
o histórico de respostas anteriores permanece em BriefingEvent.

`state` reflete o estado DA PERGUNTA:

    pending               → ainda não respondida
    answered              → respondida e sem pendências
    pending_clarification → cliente sinalizou dúvida
    review_requested      → cliente pediu nova oportunidade de responder

`transcription_status` é INDEPENDENTE do estado da resposta.

PRESERVAÇÃO DO ÁUDIO
--------------------
`latest_audio` usa PROTECT. Um Document que representa um áudio
de resposta de briefing NÃO pode ser excluído enquanto a projeção
existir. Isso garante o requisito "preserve o arquivo de áudio
original". Se for necessário remover o áudio, o caminho é excluir
o Briefing inteiro — DELETE real em cascata.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class BriefingAnswer(models.Model):

    STATE_PENDING = 'pending'
    STATE_ANSWERED = 'answered'
    STATE_PENDING_CLARIFICATION = 'pending_clarification'
    STATE_REVIEW_REQUESTED = 'review_requested'

    STATE_CHOICES = [
        (STATE_PENDING, 'Aguardando resposta'),
        (STATE_ANSWERED, 'Respondida'),
        (STATE_PENDING_CLARIFICATION, 'Dúvida aberta'),
        (STATE_REVIEW_REQUESTED, 'Revisão solicitada'),
    ]

    TRANSCRIPTION_PENDING = 'pending'
    TRANSCRIPTION_PROCESSING = 'processing'
    TRANSCRIPTION_COMPLETED = 'completed'
    TRANSCRIPTION_FAILED = 'failed'
    TRANSCRIPTION_NOT_APPLICABLE = 'not_applicable'

    TRANSCRIPTION_STATUS_CHOICES = [
        (TRANSCRIPTION_PENDING, 'Aguardando processamento'),
        (TRANSCRIPTION_PROCESSING, 'Processando'),
        (TRANSCRIPTION_COMPLETED, 'Concluída'),
        (TRANSCRIPTION_FAILED, 'Falhou'),
        (TRANSCRIPTION_NOT_APPLICABLE, 'Não aplicável'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    briefing = models.ForeignKey(
        'briefings.Briefing',
        on_delete=models.CASCADE,
        related_name='answers',
    )

    question_id = models.UUIDField(
        db_index=True,
        help_text=_('UUID da pergunta no snapshot da estrutura'),
    )

    state = models.CharField(
        max_length=30,
        choices=STATE_CHOICES,
        default=STATE_PENDING,
        db_index=True,
    )

    latest_content = models.TextField(
        blank=True,
        help_text=_('Texto da resposta mais recente (se aplicável)'),
    )

    latest_audio = models.ForeignKey(
        'documents.Document',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='briefing_answer_audio',
        help_text=_(
            'Áudio original enviado pelo cliente. PROTECT: o Document '
            'não pode ser excluído enquanto esta projeção existir.'
        ),
    )

    latest_transcription = models.TextField(
        blank=True,
        help_text=_('Transcrição do áudio mais recente'),
    )

    transcription_status = models.CharField(
        max_length=20,
        choices=TRANSCRIPTION_STATUS_CHOICES,
        default=TRANSCRIPTION_NOT_APPLICABLE,
        db_index=True,
    )

    latest_event = models.ForeignKey(
        'briefings.BriefingEvent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='answers_as_latest',
        help_text=_('Evento que originou o estado atual'),
    )

    attachments = models.ManyToManyField(
        'documents.Document',
        blank=True,
        related_name='briefing_answer_attachments',
        help_text=_('Imagens anexadas a esta resposta'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'briefing_answer'
        verbose_name = _('Resposta de Briefing')
        verbose_name_plural = _('Respostas de Briefing')
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['briefing', 'question_id'],
                name='briefing_answer_unique_per_question',
            ),
        ]
        indexes = [
            models.Index(fields=['briefing', 'state']),
            models.Index(fields=['briefing', 'transcription_status']),
        ]

    def __str__(self):
        return f"{self.briefing_id} · {self.question_id} · {self.state}"