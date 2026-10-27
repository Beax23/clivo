"""
AnalysisJob — fila de trabalho da Inteligência.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class AnalysisJob(models.Model):

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendente'),
        (STATUS_PROCESSING, 'Em processamento'),
        (STATUS_COMPLETED, 'Concluído'),
        (STATUS_FAILED, 'Falhou'),
    ]

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False,
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='analysis_jobs',
        db_index=True,
    )
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='analysis_jobs',
        db_index=True,
    )
    briefing = models.ForeignKey(
        'briefings.Briefing',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='analysis_jobs',
    )

    target_kinds = models.JSONField(default=list)
    data_version = models.CharField(max_length=100)

    job_key = models.CharField(
        max_length=512, unique=True, editable=False, db_index=True,
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES,
        default=STATUS_PENDING, db_index=True,
    )
    attempt_count = models.PositiveIntegerField(default=0)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    last_error_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'intelligence_analysis_job'
        verbose_name = _('Job de Análise')
        verbose_name_plural = _('Jobs de Análise')
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['client', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f'{self.status} · {self.workspace_id} · {self.id}'