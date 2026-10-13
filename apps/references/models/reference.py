"""
Modelo Reference.
"""

import os
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Reference(models.Model):

    SOURCE_UPLOAD = 'upload'
    SOURCE_PINTEREST = 'pinterest'
    SOURCE_GDRIVE = 'gdrive'
    SOURCE_URL = 'url'

    SOURCE_CHOICES = [
        (SOURCE_UPLOAD, 'Upload'),
        (SOURCE_PINTEREST, 'Pinterest'),
        (SOURCE_GDRIVE, 'Google Drive'),
        (SOURCE_URL, 'URL'),
    ]

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False,
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='references',
        help_text=_('Workspace ao qual a referência pertence'),
    )

    title = models.CharField(
        max_length=255,
        help_text=_('Título curto da referência'),
    )

    image = models.FileField(
        upload_to='references/',
        max_length=500,
        help_text=_('Imagem de referência.'),
    )

    extension = models.CharField(
        max_length=20, blank=True,
        help_text=_('Extensão em minúsculas (ex: "jpg")'),
    )

    size = models.BigIntegerField(
        default=0,
        help_text=_('Tamanho em bytes'),
    )

    description = models.TextField(
        blank=True,
        help_text=_('Por que essa referência importa?'),
    )

    # ------------------------------------------------------------------
    # CATEGORIAS (M2M)
    # ------------------------------------------------------------------

    categories = models.ManyToManyField(
        'references.ReferenceCategory',
        related_name='references',
        blank=True,
        help_text=_('Categorias associadas à referência.'),
    )

    # ------------------------------------------------------------------
    # PASTA (agrupamento visual)
    # ------------------------------------------------------------------

    folder = models.ForeignKey(
        'references.ReferenceFolder',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='references',
        help_text=_('Pasta onde a referência está. NULL = solta.'),
    )

    # ------------------------------------------------------------------
    # CONTEXTO
    # ------------------------------------------------------------------

    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='references',
        help_text=_('Cliente associado (opcional)'),
    )

    project_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text=_('ID de `projects.Project` (UUID solto).'),
    )

    # ------------------------------------------------------------------
    # ORIGEM
    # ------------------------------------------------------------------

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_UPLOAD,
        db_index=True,
        help_text=_('Como a imagem entrou no Clivo'),
    )

    source_url = models.URLField(
        max_length=1000, blank=True,
        help_text=_('URL de origem. Apenas histórico.'),
    )

    # ------------------------------------------------------------------
    # VISIBILIDADE
    # ------------------------------------------------------------------

    visible_to_client = models.BooleanField(
        default=False, db_index=True,
        help_text=_('Se True, o cliente também vê.'),
    )

    metadata = models.JSONField(
        null=True, blank=True,
        help_text=_('Dados extras.'),
    )

    # ------------------------------------------------------------------
    # RASTREABILIDADE
    # ------------------------------------------------------------------

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_references',
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='updated_references',
    )

    class Meta:
        db_table = 'reference'
        verbose_name = _('Referência')
        verbose_name_plural = _('Referências')
        indexes = [
            models.Index(fields=['workspace', '-created_at']),
            models.Index(fields=['workspace', 'client']),
            models.Index(fields=['workspace', 'project_id']),
            models.Index(fields=['workspace', 'folder']),
            models.Index(fields=['workspace', 'title']),
            models.Index(fields=['workspace', 'source']),
            models.Index(fields=['workspace', 'visible_to_client']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def has_client(self) -> bool:
        return self.client_id is not None

    @property
    def has_project(self) -> bool:
        return self.project_id is not None

    @property
    def has_folder(self) -> bool:
        return self.folder_id is not None

    @property
    def has_context(self) -> bool:
        return self.has_client or self.has_project

    @property
    def source_display(self) -> str:
        return self.get_source_display()

    @property
    def file_type_display(self) -> str:
        if self.extension:
            return self.extension.upper()
        if self.image and self.image.name:
            ext = os.path.splitext(self.image.name)[1].lstrip('.').lower()
            if ext:
                return ext.upper()
        return ''

    @property
    def image_size_display(self) -> str:
        size = self.size or 0
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        if size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        return f"{size / (1024 * 1024 * 1024):.2f} GB"

    @staticmethod
    def extract_extension(filename: str) -> str:
        if not filename:
            return ''
        ext = os.path.splitext(filename)[1]
        return ext.lstrip('.').lower() if ext else ''

    @staticmethod
    def extract_name(filename: str) -> str:
        if not filename:
            return ''
        return os.path.splitext(filename)[0] or filename