"""
AnalysisRun — execução concreta de uma análise.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class AnalysisRun(models.Model):

    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_SKIPPED_STALE = 'skipped_stale'

    STATUS_CHOICES = [
        (STATUS_RUNNING, 'Em execução'),
        (STATUS_COMPLETED, 'Concluído'),
        (STATUS_FAILED, 'Falhou'),
        (STATUS_SKIPPED_STALE, 'Descartado (stale)'),
    ]

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False,
    )

    job = models.ForeignKey(
        'intelligence.AnalysisJob',
        on_delete=models.CASCADE,
        related_name='runs',
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='analysis_runs',
        db_index=True,
    )
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='analysis_runs',
        db_index=True,
    )
    briefing = models.ForeignKey(
        'briefings.Briefing',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analysis_runs',
    )

    input_hash = models.CharField(
        max_length=64, unique=True, db_index=True, editable=False,
    )
    data_version = models.CharField(max_length=100)

    provider = models.CharField(max_length=50)
    model = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=50)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, db_index=True,
    )

    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)

    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    error_message = models.TextField(blank=True, default='')
    is_stale = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'intelligence_analysis_run'
        verbose_name = _('Run de Análise')
        verbose_name_plural = _('Runs de Análise')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['client', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f'{self.status} · {self.model} · {self.id}'