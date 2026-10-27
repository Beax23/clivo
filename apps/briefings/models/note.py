"""
Modelo BriefingNote — Journal privado do arquiteto.

REGRA ARQUITETURAL
------------------
Notas privadas do escritório sobre um briefing.

    - Nunca são expostas no portal do cliente.
    - Nunca são enviadas automaticamente para Intelligence.
    - Podem ser gerais (sobre o briefing) ou vinculadas a uma
      pergunta específica do snapshot.

Exclusão é REAL (DELETE), sem soft delete.

Autoria é obrigatória. Histórico de edições não é versionado
linha a linha — o `updated_at` é a última palavra. Se você quiser
versionar, deve ir para uma tabela à parte. Nesta versão,
mantemos simples.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class BriefingNote(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    briefing = models.ForeignKey(
        'briefings.Briefing',
        on_delete=models.CASCADE,
        related_name='notes',
    )

    question_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            'UUID da pergunta no snapshot. NULL = nota geral '
            'sobre o briefing.'
        ),
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='briefing_notes',
        help_text=_('Usuário do escritório que criou a nota'),
    )

    content = models.TextField(
        help_text=_('Conteúdo da anotação'),
    )

    is_pinned = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_('Se True, a nota aparece no topo da lista.'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'briefing_note'
        verbose_name = _('Anotação de Briefing')
        verbose_name_plural = _('Anotações de Briefing')
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['briefing', '-created_at']),
            models.Index(fields=['briefing', 'question_id']),
            models.Index(fields=['author']),
            models.Index(fields=['briefing', '-is_pinned', '-created_at']),
        ]

    def __str__(self):
        scope = (
            f'Q:{str(self.question_id)[:8]}' if self.question_id
            else 'geral'
        )
        pin = ' 📌' if self.is_pinned else ''
        return f"Note {self.briefing_id} · {scope}{pin}"