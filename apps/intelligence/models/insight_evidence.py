"""
InsightEvidence — evidência de um InsightItem.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class InsightEvidence(models.Model):

    SOURCE_TYPE_BRIEFING_ANSWER = 'briefing.answer'
    SOURCE_TYPE_BRIEFING_NOTE = 'briefing.note'
    SOURCE_TYPE_CLIENT_CONTEXT = 'client.context'

    SOURCE_TYPE_CHOICES = [
        (SOURCE_TYPE_BRIEFING_ANSWER, 'Resposta de briefing'),
        (SOURCE_TYPE_BRIEFING_NOTE, 'Nota de briefing'),
        (SOURCE_TYPE_CLIENT_CONTEXT, 'Contexto do cliente'),
    ]

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False,
    )

    insight = models.ForeignKey(
        'intelligence.InsightItem',
        on_delete=models.CASCADE,
        related_name='evidences',
    )

    source_type = models.CharField(
        max_length=30, choices=SOURCE_TYPE_CHOICES, db_index=True,
    )
    source_ref = models.CharField(max_length=255, db_index=True)
    quote = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'intelligence_insight_evidence'
        verbose_name = _('Evidência de Insight')
        verbose_name_plural = _('Evidências de Insight')
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['insight', 'source_type', 'source_ref'],
                name='intelligence_insight_evidence_unique_source',
            ),
        ]
        indexes = [
            models.Index(fields=['insight', 'source_type']),
            models.Index(fields=['source_type', 'source_ref']),
        ]

    def __str__(self):
        return f'{self.source_type} · {self.source_ref[:40]}'