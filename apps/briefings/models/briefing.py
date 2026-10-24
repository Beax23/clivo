"""
Modelo Briefing — execução de um template para um cliente.

REGRA ARQUITETURAL
------------------
Briefing é uma EXECUÇÃO. Não é o template.

O snapshot da estrutura é copiado no momento da criação. Alterar o
template posteriormente NÃO altera esta execução.

Referências:
    template_id          → BriefingTemplate (SET_NULL)
    template_version_id  → BriefingTemplateVersion (SET_NULL)

CUSTOM QUESTIONS
----------------
`custom_questions` (via BriefingQuestionInstance) só podem ser
adicionadas/removidas enquanto o briefing NÃO tem nenhuma resposta.

INTRO
-----
`intro_message` é o texto de apresentação mostrado ao cliente antes
da primeira pergunta. É copiado do template na criação, mas pode ser
sobrescrito individualmente.

`intro_seen_at` marca quando o cliente clicou em "Iniciar jornada".
Depois disso, a apresentação NÃO reaparece.

ESTADOS
-------
    in_progress   Em andamento (aceita resposta)
    paused        Arquiteto pausou (não aceita resposta)
    completed     Cliente respondeu tudo
    cancelled     Encerrado manualmente ou prazo expirou
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Briefing(models.Model):

    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_PAUSED = 'paused'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, 'Em andamento'),
        (STATUS_PAUSED, 'Pausado'),
        (STATUS_COMPLETED, 'Concluído'),
        (STATUS_CANCELLED, 'Cancelado'),
    ]

    PORTAL_NOT_STARTED = 'not_started'
    PORTAL_IN_PROGRESS = 'in_progress'
    PORTAL_PAUSED = 'paused'
    PORTAL_COMPLETED = 'completed'
    PORTAL_CANCELLED = 'cancelled'
    PORTAL_REOPENED = 'reopened'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='briefings',
    )

    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='briefings',
    )

    template = models.ForeignKey(
        'briefings.BriefingTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executions',
        help_text=_('Template lógico de origem (referência histórica)'),
    )

    template_version = models.ForeignKey(
        'briefings.BriefingTemplateVersion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executions',
        help_text=_(
            'Versão concreta do modelo usada nesta execução. '
            'NULL se o modelo ou a versão foram excluídos.'
        ),
    )

    title = models.CharField(
        max_length=200,
        help_text=_('Título da execução (herdado do template na criação)'),
    )

    structure_snapshot = models.JSONField(
        default=dict,
        help_text=_(
            'Snapshot imutável da estrutura (sessões e perguntas) '
            'copiado do template no momento da criação, incluindo '
            'perguntas exclusivas adicionadas antes do congelamento.'
        ),
    )

    # ---------- INTRO ----------
    intro_message = models.TextField(
        blank=True,
        help_text=_(
            'Texto de apresentação mostrado ao cliente antes da '
            'primeira pergunta. Copiado do template na criação; '
            'pode ser sobrescrito individualmente. Vazio = sem intro.'
        ),
    )

    intro_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            'Quando o cliente clicou em "Iniciar jornada". '
            'NULL = cliente ainda não viu a apresentação.'
        ),
    )

    # ---------- ESTADO ----------
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_IN_PROGRESS,
        db_index=True,
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_('Prazo opcional definido pelo arquiteto'),
    )

    started_at = models.DateTimeField(
        default=timezone.now,
        help_text=_('Quando o briefing foi criado'),
    )

    first_opened_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            'Primeira vez que o cliente abriu o briefing no portal. '
            'NULL = cliente nunca abriu (não iniciado).'
        ),
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Quando o cliente concluiu todas as obrigatórias'),
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            'Quando o briefing foi cancelado (manualmente ou por '
            'expiração do prazo).'
        ),
    )

    has_custom_questions = models.BooleanField(
        default=False,
        help_text=_(
            'Indica que o arquiteto adicionou perguntas exclusivas '
            'a esta execução, fora do template original.'
        ),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_briefings',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'briefing'
        verbose_name = _('Briefing')
        verbose_name_plural = _('Briefings')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['client', 'status']),
            models.Index(fields=['workspace', '-created_at']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['template_version']),
            models.Index(fields=['first_opened_at']),
        ]

    def __str__(self):
        return f"{self.title} — {self.client.name}"

    # ------------------------------------------------------------------
    # INTRO
    # ------------------------------------------------------------------

    def has_intro(self) -> bool:
        return bool((self.intro_message or '').strip())

    def show_intro_to_portal(self) -> bool:
        if not self.has_intro():
            return False
        if self.intro_seen_at is not None:
            return False
        return self.status == self.STATUS_IN_PROGRESS

    def mark_intro_seen(self):
        if self.intro_seen_at is None:
            self.intro_seen_at = timezone.now()
            self.save(update_fields=['intro_seen_at', 'updated_at'])

    # ------------------------------------------------------------------
    # ESTADO
    # ------------------------------------------------------------------

    def is_answerable(self) -> bool:
        if self.status != self.STATUS_IN_PROGRESS:
            return False
        if self.expires_at and timezone.now() >= self.expires_at:
            return False
        return True

    def has_expired(self) -> bool:
        if not self.expires_at:
            return False
        return timezone.now() >= self.expires_at

    def mark_expired_if_needed(self) -> bool:
        if (
            self.status in (
                self.STATUS_IN_PROGRESS,
                self.STATUS_PAUSED,
            )
            and self.has_expired()
        ):
            self.status = self.STATUS_CANCELLED
            self.cancelled_at = timezone.now()
            self.save(update_fields=[
                'status', 'cancelled_at', 'updated_at',
            ])
            return True
        return False

    def is_snapshot_locked(self) -> bool:
        return self.answers.exists()

    def has_available_origin(self) -> bool:
        if self.template_version_id is None:
            return False
        if self.template_version is None:
            return False
        return True

    # ------------------------------------------------------------------
    # STATUS DERIVADO PARA O PORTAL
    # ------------------------------------------------------------------

    def portal_status(self) -> str:
        if self.status == self.STATUS_PAUSED:
            return self.PORTAL_PAUSED

        if self.status == self.STATUS_COMPLETED:
            if self.completed_at and self._was_reopened_since(
                self.completed_at,
            ):
                return self.PORTAL_REOPENED
            return self.PORTAL_COMPLETED

        if self.status == self.STATUS_CANCELLED:
            if self.cancelled_at and self._was_reopened_since(
                self.cancelled_at,
            ):
                return self.PORTAL_REOPENED
            return self.PORTAL_CANCELLED

        if self.status == self.STATUS_IN_PROGRESS:
            if not self.first_opened_at:
                return self.PORTAL_NOT_STARTED
            if self._was_reopened_since_last_terminal():
                return self.PORTAL_REOPENED
            return self.PORTAL_IN_PROGRESS

        return self.PORTAL_IN_PROGRESS

    def portal_can_answer(self) -> bool:
        return self.portal_status() in (
            self.PORTAL_NOT_STARTED,
            self.PORTAL_IN_PROGRESS,
            self.PORTAL_REOPENED,
        )

    # ------------------------------------------------------------------
    # HELPERS "REOPENED"
    # ------------------------------------------------------------------

    def _was_reopened_since(self, timestamp) -> bool:
        from apps.briefings.models.briefing_event import BriefingEvent
        if timestamp is None:
            return False
        return self.events.filter(
            kind=BriefingEvent.KIND_REOPENED,
            created_at__gt=timestamp,
        ).exists()

    def _was_reopened_since_last_terminal(self) -> bool:
        terminal = None
        if self.completed_at and self.cancelled_at:
            terminal = max(self.completed_at, self.cancelled_at)
        elif self.completed_at:
            terminal = self.completed_at
        elif self.cancelled_at:
            terminal = self.cancelled_at

        if terminal is None:
            return False
        return self._was_reopened_since(terminal)

    # ------------------------------------------------------------------
    # SNAPSHOT
    # ------------------------------------------------------------------

    def snapshot_questions(self) -> list:
        result = []
        sections = sorted(
            self.structure_snapshot.get('sections', []),
            key=lambda s: s.get('position', 0),
        )
        for section in sections:
            questions = sorted(
                section.get('questions', []),
                key=lambda q: q.get('position', 0),
            )
            for q in questions:
                result.append({
                    **q,
                    'section_id': section.get('id'),
                    'section_title': section.get('title'),
                })
        return result

    def snapshot_question_by_id(self, question_id: str) -> dict:
        for q in self.snapshot_questions():
            if str(q.get('id')) == str(question_id):
                return q
        return None