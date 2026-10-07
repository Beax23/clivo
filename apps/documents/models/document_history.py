"""
Modelo DocumentHistory.

Registra cada alteração feita em um Document.

REGRA ARQUITETURAL
------------------
`DocumentHistory` é o registro histórico do ciclo de vida do arquivo.
Ele não armazena o arquivo. Ele armazena o que aconteceu com ele.

Ações registradas:

    created               → arquivo foi subido
    renamed               → nome alterado
    replaced              → arquivo físico substituído
    client_associated     → cliente vinculado
    client_removed        → cliente desvinculado
    project_associated    → projeto vinculado
    project_removed       → projeto desvinculado
    deleted               → arquivo excluído

Download NÃO é registrado como alteração. Download é acesso, não
mudança de estado. Se um dia houver necessidade de auditar acesso,
isso será uma estrutura própria (não o histórico de alterações).

SOBRE `previous_value` E `new_value`
------------------------------------
Campos JSONField genéricos, NULLABLE.

Cada ação preenche o que fizer sentido:

    renamed
        previous_value = {"name": "briefing"}
        new_value      = {"name": "briefing-final"}

    client_associated
        previous_value = {"client_id": None}
        new_value      = {"client_id": "<uuid>"}

Não criamos campos específicos por ação. previous/new genéricos
resolvem todos os casos sem inflar o schema.

SOBRE `document` NULLABLE
-------------------------
`document` é FK nullable com SET_NULL.

Quando um Document é excluído:
    - o arquivo físico é removido
    - o registro em `Document` é apagado
    - o FK em `DocumentHistory` recebe NULL

Isso preserva a auditoria (quem excluiu, quando) sem preservar o
arquivo. O histórico com `action='deleted'` fica órfão de FK mas
permanece consultável.

SOBRE `user`
------------
`user` é FK nullable com SET_NULL.

Se o usuário que fez a ação for excluído do Clivo, o histórico
permanece com `user = NULL`. O `timestamp` e a `action` permanecem.

SOBRE IMUTABILIDADE
-------------------
`DocumentHistory` é APPEND-ONLY.

Não existe update. Não existe delete. Cada linha é um fato
ocorrido, e fatos não mudam.

Views de histórico só permitem leitura.
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
    ACTION_DELETED = 'deleted'

    ACTION_CHOICES = [
        (ACTION_CREATED, 'Arquivo criado'),
        (ACTION_RENAMED, 'Renomeado'),
        (ACTION_REPLACED, 'Arquivo substituído'),
        (ACTION_CLIENT_ASSOCIATED, 'Cliente associado'),
        (ACTION_CLIENT_REMOVED, 'Cliente removido'),
        (ACTION_PROJECT_ASSOCIATED, 'Projeto associado'),
        (ACTION_PROJECT_REMOVED, 'Projeto removido'),
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
        help_text=_(
            'Estado anterior (quando aplicável). '
            'NULL para ações que não possuem estado anterior.'
        ),
    )

    new_value = models.JSONField(
        null=True,
        blank=True,
        help_text=_(
            'Estado novo (quando aplicável). '
            'NULL para ações que não geram novo estado.'
        ),
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