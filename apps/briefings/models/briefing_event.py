"""
Modelo BriefingEvent — histórico imutável da conversa.

REGRA ARQUITETURAL
------------------
Eventos são APPEND-ONLY. Nunca editados, nunca apagados.

Cada linha descreve UM fato ocorrido. O estado atual é derivado
dos eventos mais recentes (via BriefingAnswer), mas o histórico
completo permanece.

AUTORIA
-------
Um evento pode ser criado por:

    - um usuário autenticado do escritório (User)
    - uma sessão autenticada do portal do cliente (ClientPortalSession)
    - o próprio sistema (envio de e-mail, notificações internas)

Exatamente UM dos dois deve estar preenchido. Uma constraint
CheckConstraint garante isso no banco. Eventos de sistema também
gravam a FK `user=None, portal_session=None` — mas eles são
criados somente pelo próprio serviço interno.

NOTA SOBRE ANÁLISE
------------------
Análise de IA NÃO vive aqui. Pertence ao app `intelligence`.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class BriefingEvent(models.Model):

    # ------------------------------------------------------------------
    # TIPOS DE EVENTO
    # ------------------------------------------------------------------

    KIND_ANSWERED = 'answered'
    KIND_CLARIFICATION_REQUESTED = 'clarification_requested'
    KIND_REVIEW_REQUESTED = 'review_requested'
    KIND_TRANSCRIPTION_GENERATED = 'transcription_generated'
    KIND_ANALYSIS_GENERATED = 'analysis_generated'
    KIND_PAUSED = 'paused'
    KIND_RESUMED = 'resumed'
    KIND_REOPENED = 'reopened'
    KIND_COMPLETED = 'completed'
    KIND_CLOSED = 'closed'
    KIND_EXPIRED = 'expired'
    KIND_COMPLETION_EMAIL_SENT = 'completion_email_sent'
    KIND_MANUAL_SEND = 'manual_send'

    KIND_CHOICES = [
        (KIND_ANSWERED, 'Resposta registrada'),
        (KIND_CLARIFICATION_REQUESTED, 'Dúvida solicitada pelo cliente'),
        (KIND_REVIEW_REQUESTED, 'Revisão solicitada pelo cliente'),
        (KIND_TRANSCRIPTION_GENERATED, 'Transcrição gerada'),
        (KIND_ANALYSIS_GENERATED, 'Análise gerada'),
        (KIND_PAUSED, 'Briefing pausado'),
        (KIND_RESUMED, 'Briefing retomado'),
        (KIND_REOPENED, 'Briefing reaberto'),
        (KIND_COMPLETED, 'Briefing concluído'),
        (KIND_CLOSED, 'Briefing encerrado pelo arquiteto'),
        (KIND_EXPIRED, 'Briefing expirado'),
        (KIND_COMPLETION_EMAIL_SENT, 'E-mail de conclusão enviado'),
        (KIND_MANUAL_SEND, 'Briefing enviado manualmente'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    briefing = models.ForeignKey(
        'briefings.Briefing',
        on_delete=models.CASCADE,
        related_name='events',
    )

    kind = models.CharField(
        max_length=40,
        choices=KIND_CHOICES,
        db_index=True,
    )

    question_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_('UUID da pergunta alvo (quando aplicável)'),
    )

    content = models.JSONField(
        default=dict,
        blank=True,
        help_text=_('Payload específico do tipo de evento'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='briefing_events_as_user',
        help_text=_('Autor do escritório (se aplicável)'),
    )

    portal_session = models.ForeignKey(
        'clients.ClientPortalSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='briefing_events_as_portal',
        help_text=_('Sessão do portal do cliente (se aplicável)'),
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'briefing_event'
        verbose_name = _('Evento de Briefing')
        verbose_name_plural = _('Eventos de Briefing')
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, portal_session__isnull=True)
                    | models.Q(user__isnull=True, portal_session__isnull=False)
                    | models.Q(user__isnull=True, portal_session__isnull=True)
                ),
                name='briefing_event_unique_author',
            ),
        ]
        indexes = [
            models.Index(fields=['briefing', '-created_at']),
            models.Index(fields=['briefing', 'kind', '-created_at']),
            models.Index(fields=['question_id', '-created_at']),
        ]

    def __str__(self):
        author = (
            self.user.email if self.user
            else (str(self.portal_session_id) if self.portal_session
                  else 'system')
        )
        return f"{self.briefing_id} · {self.kind} · {author}"