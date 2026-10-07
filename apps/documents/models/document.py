"""
Modelo Document.

Representa um arquivo conhecido pelo Clivo.

REGRA ARQUITETURAL
------------------
`Document` é o arquivo físico + metadados + contexto.

Ele NÃO é:
    - pasta
    - tag
    - versão
    - comentário
    - aprovação
    - OCR
    - editor de conteúdo

`Document` É:
    "isto é um arquivo que o Clivo conhece."

SOBRE O CAMPO `file`
--------------------
Usamos `FileField` do Django. O storage é decidido pelo projeto
(`DEFAULT_FILE_STORAGE`). Se o projeto estiver com Cloudinary, usa
Cloudinary. Se estiver com `MEDIA_ROOT` local, usa local.

SOBRE `extension` E `mime_type`
-------------------------------
Não há lista de extensões permitidas.

O sistema aceita arquivos de todos os tipos. O que registramos:

    - extension   → extensão em minúsculas (ex: "pdf", "m4a")
    - mime_type   → MIME type reportado pelo upload
    - size        → tamanho em bytes

SOBRE `name`
------------
`name` é o nome SEM extensão. A extensão fica em `extension`.

SOBRE `client` E `project_id`
-----------------------------
Ambos são opcionais. Um documento pode existir sem contexto.

`project_id` é UUIDField solto, NÃO é FK, porque o app `projects`
ainda não existe.

SOBRE `source`
--------------
Origem do arquivo. Define como ele entrou no Clivo:

    upload  → enviado do computador do usuário (padrão)
    gdrive  → importado do Google Drive
    url     → baixado de uma URL externa

O campo é informativo. Não muda o comportamento do Document.

`source_url` guarda a URL original (quando source='url' ou
source='gdrive'). Não é usada para sincronização. É apenas
registro histórico para o usuário saber de onde veio.

SOBRE EXCLUSÃO
--------------
DELETE É DELETE. Sem soft delete. Sem lixeira. Sem restore.
"""

import os
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Document(models.Model):

    # ------------------------------------------------------------------
    # SOURCE (origem do arquivo)
    # ------------------------------------------------------------------

    SOURCE_UPLOAD = 'upload'
    SOURCE_GDRIVE = 'gdrive'
    SOURCE_URL = 'url'

    SOURCE_CHOICES = [
        (SOURCE_UPLOAD, 'Upload'),
        (SOURCE_GDRIVE, 'Google Drive'),
        (SOURCE_URL, 'URL'),
    ]

    # ------------------------------------------------------------------
    # CAMPOS
    # ------------------------------------------------------------------

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='documents',
        help_text=_('Workspace ao qual o arquivo pertence'),
    )

    name = models.CharField(
        max_length=255,
        help_text=_('Nome do arquivo, sem extensão'),
    )

    file = models.FileField(
        upload_to='documents/',
        max_length=500,
        help_text=_(
            'Arquivo físico. O storage é definido por '
            'DEFAULT_FILE_STORAGE no projeto.'
        ),
    )

    extension = models.CharField(
        max_length=20,
        blank=True,
        help_text=_('Extensão em minúsculas, sem ponto (ex: "pdf", "m4a")'),
    )

    mime_type = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('MIME type reportado pelo upload'),
    )

    size = models.BigIntegerField(
        default=0,
        help_text=_('Tamanho do arquivo em bytes'),
    )

    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
        help_text=_('Cliente associado (opcional)'),
    )

    project_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            'ID de `projects.Project` (UUID solto até o app `projects` '
            'existir). NÃO usar como campo genérico de relacionamento.'
        ),
    )

    # ------------------------------------------------------------------
    # ORIGEM
    # ------------------------------------------------------------------

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_UPLOAD,
        db_index=True,
        help_text=_('Como o arquivo entrou no Clivo'),
    )

    source_url = models.URLField(
        max_length=1000,
        blank=True,
        help_text=_(
            'URL de origem (Google Drive, URL externa). '
            'Apenas registro histórico — não é usada para sincronização.'
        ),
    )

    # ------------------------------------------------------------------
    # RASTREABILIDADE
    # ------------------------------------------------------------------

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_documents',
        help_text=_('Usuário que subiu o arquivo'),
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_documents',
        help_text=_('Usuário que fez a última alteração'),
    )

    class Meta:
        db_table = 'document'
        verbose_name = _('Arquivo')
        verbose_name_plural = _('Arquivos')
        indexes = [
            models.Index(fields=['workspace', '-created_at']),
            models.Index(fields=['workspace', 'client']),
            models.Index(fields=['workspace', 'project_id']),
            models.Index(fields=['workspace', 'name']),
            models.Index(fields=['workspace', 'source']),
            models.Index(fields=['extension']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return self.full_name

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @property
    def full_name(self) -> str:
        if self.extension:
            return f"{self.name}.{self.extension}"
        return self.name

    @property
    def has_client(self) -> bool:
        return self.client_id is not None

    @property
    def has_project(self) -> bool:
        return self.project_id is not None

    @property
    def has_context(self) -> bool:
        """Um documento tem contexto quando tem cliente OU projeto."""
        return self.has_client or self.has_project

    @property
    def size_display(self) -> str:
        size = self.size or 0
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        if size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        return f"{size / (1024 * 1024 * 1024):.2f} GB"

    @property
    def source_display(self) -> str:
        return self.get_source_display()

    # ------------------------------------------------------------------
    # EXTRAÇÃO DE METADADOS
    # ------------------------------------------------------------------

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