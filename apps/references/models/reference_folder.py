"""
Modelo ReferenceFolder.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ReferenceFolder(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='reference_folders',
        help_text=_('Workspace ao qual a pasta pertence'),
    )

    name = models.CharField(
        max_length=100,
        help_text=_('Nome da pasta'),
    )

    cover = models.FileField(
        upload_to='reference-folders/covers/',
        max_length=500,
        blank=True,
        null=True,
        help_text=_(
            'Imagem de capa da pasta. Opcional. Se ausente, o frontend '
            'mostra o ícone de pasta no lugar.'
        ),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_reference_folders',
        help_text=_('Usuário que criou a pasta'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reference_folder'
        verbose_name = _('Pasta de Referências')
        verbose_name_plural = _('Pastas de Referências')
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'name'],
                name='reference_folder_unique_name_per_workspace',
            ),
        ]
        indexes = [
            models.Index(fields=['workspace', 'name']),
            models.Index(fields=['workspace', '-created_at']),
        ]

    def __str__(self):
        return self.name

    @property
    def reference_count(self) -> int:
        return self.references.count()