"""
Modelo DocumentHistory.

Registra cada alteração feita em um Document.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentHistory(models.Model):

    # ------------------------------------------------------------------
    # AÇÕES
    # ------------------------------------------------------------------

    ACTION_CREATED = 'created'
    ACTION_RENAMED = 'renamed'
    ACTION_REPLACED = 'replaced'
    ACTION_CLIENT_ASSOCIATED = 'client_associated'
    ACTION_CLIENT_REMOVED = 'client_removed'
    ACTION_PROJECT_ASSOCIATED = 'project_associated'
    ACTION_PROJECT_REMOVED = 'project_removed'
    ACTION_MOVED = 'moved'
    ACTION_VISIBILITY_CHANGED = 'visibility_changed'
    ACTION_DELETED = 'deleted'

    ACTION_CHOICES = [
        (ACTION_CREATED, 'Arquivo criado'),
        (ACTION_RENAMED, 'Renomeado'),
        (ACTION_REPLACED, 'Arquivo substituído'),
        (ACTION_CLIENT_ASSOCIATED, 'Cliente associado'),
        (ACTION_CLIENT_REMOVED, 'Cliente removido'),
        (ACTION_PROJECT_ASSOCIATED, 'Projeto associado'),
        (ACTION_PROJECT_REMOVED, 'Projeto removido'),
        (ACTION_MOVED, 'Movido de pasta'),
        (ACTION_VISIBILITY_CHANGED, 'Visibilidade alterada'),
        (ACTION_DELETED, 'Excluído'),
    ]

    # ------------------------------------------------------------------
    # CAMPOS
    # ------------------------------------------------------------------

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    document = models.ForeignKey(
        'documents.Document',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='history',
        help_text=_(
            'Documento ao qual este registro se refere. '
            'NULL quando o documento já foi excluído.'
        ),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='document_history_entries',
        help_text=_('Usuário que executou a ação'),
    )

    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
        db_index=True,
        help_text=_('Ação executada sobre o documento'),
    )

    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text=_('Momento em que a ação ocorreu'),
    )

    previous_value = models.JSONField(
        null=True,
        blank=True,
        help_text=_('Estado anterior (quando aplicável).'),
    )

    new_value = models.JSONField(
        null=True,
        blank=True,
        help_text=_('Estado novo (quando aplicável).'),
    )

    class Meta:
        db_table = 'document_history'
        verbose_name = _('Histórico de Arquivo')
        verbose_name_plural = _('Históricos de Arquivo')
        indexes = [
            models.Index(fields=['document', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['-timestamp']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        doc_label = str(self.document) if self.document else 'documento excluído'
        return f"{self.action} · {doc_label}"