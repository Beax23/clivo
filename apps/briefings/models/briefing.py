"""
Modelo Briefing — execução de um template para um cliente.

REGRA ARQUITETURAL
------------------
Briefing é uma EXECUÇÃO. Não é o template.

O snapshot da estrutura é copiado no momento da criação. Alterar o
template posteriormente NÃO altera esta execução.

Estados do briefing (`status`):

    in_progress  → briefing em andamento, aceita respostas
    paused       → interrupção temporária, NÃO aceita respostas
    completed    → cliente respondeu todas as perguntas obrigatórias
    closed       → encerrado explicitamente pelo arquiteto
    expired      → passou do prazo e não foi concluído

`expires_at` é opcional. Se definido, o briefing expira quando o
prazo passa e o status é `in_progress`.

NOTA SOBRE ANÁLISE
------------------
Análise de IA NÃO vive aqui. Pertence ao app `intelligence`. Este
modelo só expõe os dados brutos que `intelligence` pode consumir.
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
    STATUS_CLOSED = 'closed'
    STATUS_EXPIRED = 'expired'

    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, 'Em andamento'),
        (STATUS_PAUSED, 'Pausado'),
        (STATUS_COMPLETED, 'Concluído'),
        (STATUS_CLOSED, 'Encerrado'),
        (STATUS_EXPIRED, 'Expirado'),
    ]

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
        help_text=_('Template de origem (referência histórica)'),
    )

    title = models.CharField(
        max_length=200,
        help_text=_('Título da execução (herdado do template na criação)'),
    )

    structure_snapshot = models.JSONField(
        default=dict,
        help_text=_(
            'Snapshot imutável da estrutura (sessões e perguntas) '
            'copiado do template no momento da criação.'
        ),
    )

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

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Quando o cliente concluiu todas as obrigatórias'),
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Quando o arquiteto encerrou o briefing'),
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
        ]

    def __str__(self):
        return f"{self.title} — {self.client.name}"

    # ------------------------------------------------------------------
    # ESTADO
    # ------------------------------------------------------------------

    def is_answerable(self) -> bool:
        """Se o cliente pode enviar respostas agora."""
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
        """Marca como expirado se o prazo passou e status ainda permite."""
        if (
            self.status == self.STATUS_IN_PROGRESS
            and self.has_expired()
        ):
            self.status = self.STATUS_EXPIRED
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False

    # ------------------------------------------------------------------
    # SNAPSHOT — helpers
    # ------------------------------------------------------------------

    def snapshot_questions(self) -> list:
        """Lista plana de perguntas na ordem (sessão, posição)."""
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