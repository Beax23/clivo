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
`custom_questions` (via BriefingQuestionInstance) podem ser adicionadas
enquanto o briefing NÃO tem nenhuma resposta (comportamento antigo).

PERGUNTAS COMPLEMENTARES
------------------------
A partir desta versão, perguntas adicionadas APÓS o briefing já ter
respostas vão para um bloco separado, o `supplementary_snapshot`, e
NÃO reescrevem o `structure_snapshot` original.

O snapshot original permanece imutável. O bloco complementar é
reconstruído a partir de `BriefingQuestionInstance` sempre que o
arquiteto adiciona ou remove uma pergunta.

REMOÇÃO
-------
Pergunta complementar NÃO respondida pode ser removida (DELETE real
+ evento com snapshot completo no `content`).

Pergunta complementar JÁ respondida NÃO pode ser removida. Para
corrigir, o arquiteto adiciona uma nova pergunta complementar. A
`BriefingAnswer` e os eventos originais permanecem intactos.

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
    completed     Cliente respondeu tudo do bloco original
    cancelled     Encerrado manualmente ou prazo expirou

`status` refere-se ao BLOCO ORIGINAL. O estado das perguntas
complementares é controlado separadamente por
`supplementary_completed_at`.
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
    PORTAL_SUPPLEMENTARY_PENDING = 'supplementary_pending'

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
            'copiado do template no momento da criação. '
            'NUNCA reescrito após o primeiro congelamento.'
        ),
    )

    supplementary_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            'Estrutura das perguntas complementares, separada do '
            'structure_snapshot original. Nunca reescreve o snapshot '
            'original. Formato: '
            '{"snapshot_version": 1, "sections": [...]}.'
        ),
    )

    supplementary_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            'Quando todas as perguntas complementares obrigatórias '
            'foram respondidas. NULL = ainda há pendência ou nunca '
            'houve complemento.'
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

    last_viewed_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            'Última vez que o cliente abriu o portal deste briefing. '
            'Usado para detectar perguntas complementares ainda não '
            'vistas. Diferente de first_opened_at (que só registra a '
            'primeira abertura).'
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
            models.Index(fields=['last_viewed_at']),
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

    def mark_viewed(self):
        """
        Registra a visualização atual. Atualiza SEMPRE, não só na
        primeira vez. Diferente de `first_opened_at`.
        """
        now = timezone.now()
        fields = ['last_viewed_at', 'updated_at']
        self.last_viewed_at = now
        if self.first_opened_at is None:
            self.first_opened_at = now
            fields.append('first_opened_at')
        self.save(update_fields=fields)

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
        """
        Retorna True se o snapshot ORIGINAL não pode mais ser alterado.

        Nota: esta guarda continua válida para `structure_snapshot`.
        Perguntas complementares NÃO dependem desta guarda — vão para
        `supplementary_snapshot` e são gerenciadas por
        BriefingQuestionInstanceService.
        """
        return self.answers.exists()

    def has_available_origin(self) -> bool:
        if self.template_version_id is None:
            return False
        if self.template_version is None:
            return False
        return True

    # ------------------------------------------------------------------
    # PERGUNTAS COMPLEMENTARES
    # ------------------------------------------------------------------

    def supplementary_questions(self) -> list:
        """
        Retorna a lista achatada de perguntas complementares do
        `supplementary_snapshot`, com `section_id` e `section_title`
        embutidos em cada item.
        """
        result = []
        sections = sorted(
            (self.supplementary_snapshot or {}).get('sections', []),
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

    def has_supplementary_questions(self) -> bool:
        return bool(self.supplementary_questions())

    def has_pending_supplementary(self) -> bool:
        """
        True se existe pelo menos uma pergunta complementar OBRIGATÓRIA
        sem resposta em estado ANSWERED. Perguntas opcionais não contam.
        """
        from apps.briefings.models.briefing_answer import BriefingAnswer

        questions = self.supplementary_questions()
        if not questions:
            return False

        required_ids = {
            str(q['id']) for q in questions if q.get('is_required')
        }
        if not required_ids:
            return False

        answered_ids = set(
            str(a.question_id)
            for a in BriefingAnswer.objects.filter(
                briefing=self,
                state=BriefingAnswer.STATE_ANSWERED,
            )
        )
        return not required_ids.issubset(answered_ids)

    def supplementary_state(self) -> dict:
        """
        Estado consolidado do complemento, para o portal.

        Retorna:
            {
                'has_questions': bool,
                'has_pending_required': bool,
                'count_pending_required': int,
                'count_pending_optional': int,
                'is_complete': bool,
            }
        """
        from apps.briefings.models.briefing_answer import BriefingAnswer

        questions = self.supplementary_questions()
        if not questions:
            return {
                'has_questions': False,
                'has_pending_required': False,
                'count_pending_required': 0,
                'count_pending_optional': 0,
                'is_complete': False,
            }

        answers = {
            str(a.question_id): a
            for a in BriefingAnswer.objects.filter(briefing=self)
        }

        count_pending_required = 0
        count_pending_optional = 0
        for q in questions:
            qid = str(q['id'])
            answer = answers.get(qid)
            is_answered = (
                answer is not None
                and answer.state == BriefingAnswer.STATE_ANSWERED
            )
            if is_answered:
                continue
            if q.get('is_required'):
                count_pending_required += 1
            else:
                count_pending_optional += 1

        is_complete = (
            count_pending_required == 0
            and self.supplementary_completed_at is not None
        )

        return {
            'has_questions': True,
            'has_pending_required': count_pending_required > 0,
            'count_pending_required': count_pending_required,
            'count_pending_optional': count_pending_optional,
            'is_complete': is_complete,
        }

    def mark_supplementary_completed(self):
        """
        Marca o complemento como concluído. Idempotente.
        Não altera o `status` do briefing original.
        """
        if self.supplementary_completed_at is not None:
            return
        self.supplementary_completed_at = timezone.now()
        self.save(update_fields=[
            'supplementary_completed_at', 'updated_at',
        ])

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
            if self.has_pending_supplementary():
                return self.PORTAL_SUPPLEMENTARY_PENDING
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
        """
        Se o cliente pode enviar respostas agora.

        Inclui o caso: briefing original concluído, mas complemento
        pendente. Nesse caso, o cliente PODE responder as perguntas
        complementares.
        """
        if self.portal_status() in (
            self.PORTAL_NOT_STARTED,
            self.PORTAL_IN_PROGRESS,
            self.PORTAL_REOPENED,
            self.PORTAL_SUPPLEMENTARY_PENDING,
        ):
            return True
        return False

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
    # SNAPSHOT ORIGINAL
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

    def supplementary_question_by_id(self, question_id: str) -> dict:
        for q in self.supplementary_questions():
            if str(q.get('id')) == str(question_id):
                return q
        return None

    def all_questions(self) -> list:
        """
        Concatena original + complementares, preservando a ordem de
        resposta esperada: original primeiro, complementares depois.
        """
        return list(self.snapshot_questions()) + list(
            self.supplementary_questions()
        )