"""
Modelo DocumentFolder.

Uma pasta é um agrupamento opcional de documentos dentro de um workspace.

REGRA ARQUITETURAL
------------------
Pasta é organização VISUAL, não semântica.

A organização semântica do Clivo continua sendo:
    Document → Client → Project → Briefing

Pasta é um atalho para "onde guardei isso", não "a que contexto pertence".

REGRAS
------
- Pasta pertence a UM workspace.
- Pasta tem nome único por workspace.
- Documento tem ZERO ou UMA pasta (FK opcional em Document).
- Excluir pasta NÃO exclui documentos — eles voltam a ficar soltos.
- Sem subpastas no P0. Se um dia forem necessárias, adiciona-se `parent`.
- Sem permissões por pasta no P0. Capability + workspace resolvem.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentFolder(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='document_folders',
        help_text=_('Workspace ao qual a pasta pertence'),
    )

    name = models.CharField(
        max_length=100,
        help_text=_('Nome da pasta'),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_document_folders',
        help_text=_('Usuário que criou a pasta'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'document_folder'
        verbose_name = _('Pasta de Arquivos')
        verbose_name_plural = _('Pastas de Arquivos')
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'name'],
                name='document_folder_unique_name_per_workspace',
            ),
        ]
        indexes = [
            models.Index(fields=['workspace', 'name']),
            models.Index(fields=['workspace', '-created_at']),
        ]

    def __str__(self):
        return self.name

    @property
    def document_count(self) -> int:
        """Número de documentos vivos nesta pasta."""
        return self.documents.count()