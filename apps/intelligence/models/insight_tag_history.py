"""
Histórico imutável de transições de estado de tags.

REGRA ARQUITETURAL
------------------
`InsightItem.review_state` reflete o estado ATUAL da tag. Este modelo
registra CADA transição com autor, timestamp e estado anterior.

Sem este modelo, não é possível responder:
    - Quem confirmou esta tag?
    - Quando foi descartada?
    - Qual era o estado anterior?

Toda escrita em `InsightItem.review_state` para itens de kind='tag'
DEVE passar por `TagService`, que grava uma linha aqui.

APPEND-ONLY. Nunca editado, nunca apagado.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class InsightTagHistory(models.Model):

    STATE_NEW = 'new'
    STATE_CONFIRMED = 'confirmed'
    STATE_DISCARDED = 'discarded'

    STATE_CHOICES = [
        (STATE_NEW, 'Novo'),
        (STATE_CONFIRMED, 'Confirmado'),
        (STATE_DISCARDED, 'Descartado'),
    ]

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False,
    )

    insight = models.ForeignKey(
        'intelligence.InsightItem',
        on_delete=models.CASCADE,
        related_name='tag_history',
        help_text=_('Item de tag ao qual esta transição se refere.'),
    )

    previous_state = models.CharField(
        max_length=20,
        choices=STATE_CHOICES,
        help_text=_('Estado imediatamente anterior à transição.'),
    )
    new_state = models.CharField(
        max_length=20,
        choices=STATE_CHOICES,
        help_text=_('Estado após a transição.'),
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='tag_state_changes',
        help_text=_(
            'Usuário que realizou a transição. NULL = sistema '
            '(ex.: ingestão automática).'
        ),
    )

    reason = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text=_('Motivo opcional informado pelo autor.'),
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'intelligence_insight_tag_history'
        verbose_name = _('Histórico de Tag')
        verbose_name_plural = _('Históricos de Tag')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['insight', '-created_at']),
            models.Index(fields=['changed_by', '-created_at']),
            models.Index(fields=['new_state', '-created_at']),
        ]

    def __str__(self):
        return (
            f"{self.insight_id} · {self.previous_state} → "
            f"{self.new_state} @ {self.created_at:%Y-%m-%d %H:%M}"
        )