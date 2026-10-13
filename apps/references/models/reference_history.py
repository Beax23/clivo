"""
Modelo ReferenceHistory.

Registra cada alteração feita em uma Reference.

REGRA ARQUITETURAL
------------------
`ReferenceHistory` é o registro histórico do ciclo de vida da referência.
Ele não armazena a imagem. Ele armazena o que aconteceu com ela.

Ações registradas:

    created               → referência foi criada
    renamed               → título alterado
    edited                → descrição / categoria alterada
    image_replaced        → imagem física substituída
    folder_changed        → movida para outra pasta (ou solta)
    client_associated     → cliente vinculado
    client_removed        → cliente desvinculado
    project_associated    → projeto vinculado
    project_removed       → projeto desvinculado
    visibility_changed    → visibilidade ao cliente alterada
    deleted               → referência excluída

SOBRE `previous_value` E `new_value`
------------------------------------
Campos JSONField genéricos, NULLABLE.

Cada ação preenche o que fizer sentido:

    renamed
        previous_value = {"title": "Cozinha"}
        new_value      = {"title": "Cozinha integrada"}

    client_associated
        previous_value = {"client_id": None}
        new_value      = {"client_id": "<uuid>"}

    folder_changed
        previous_value = {"folder_id": "<uuid>"}
        new_value      = {"folder_id": None}

    visibility_changed
        previous_value = {"visible_to_client": False}
        new_value      = {"visible_to_client": True}

Não criamos campos específicos por ação. previous/new genéricos
resolvem todos os casos sem inflar o schema.

SOBRE `reference` NULLABLE
--------------------------
`reference` é FK nullable com SET_NULL.

Quando uma Reference é excluída:
    - a imagem física é removida
    - o registro em `Reference` é apagado
    - o FK em `ReferenceHistory` recebe NULL

Isso preserva a auditoria (quem excluiu, quando) sem preservar
a imagem.

SOBRE `user`
------------
`user` é FK nullable com SET_NULL.

Se o usuário que fez a ação for excluído do Clivo, o histórico
permanece com `user = NULL`. O `timestamp` e a `action` permanecem.

SOBRE IMUTABILIDADE
-------------------
`ReferenceHistory` é APPEND-ONLY.

Não existe update. Não existe delete. Cada linha é um fato
ocorrido, e fatos não mudam.

Views de histórico só permitem leitura.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ReferenceHistory(models.Model):

    # ------------------------------------------------------------------
    # AÇÕES
    # ------------------------------------------------------------------

    ACTION_CREATED = 'created'
    ACTION_RENAMED = 'renamed'
    ACTION_EDITED = 'edited'
    ACTION_IMAGE_REPLACED = 'image_replaced'
    ACTION_FOLDER_CHANGED = 'folder_changed'
    ACTION_CLIENT_ASSOCIATED = 'client_associated'
    ACTION_CLIENT_REMOVED = 'client_removed'
    ACTION_PROJECT_ASSOCIATED = 'project_associated'
    ACTION_PROJECT_REMOVED = 'project_removed'
    ACTION_VISIBILITY_CHANGED = 'visibility_changed'
    ACTION_DELETED = 'deleted'

    ACTION_CHOICES = [
        (ACTION_CREATED, 'Referência criada'),
        (ACTION_RENAMED, 'Renomeada'),
        (ACTION_EDITED, 'Editada'),
        (ACTION_IMAGE_REPLACED, 'Imagem substituída'),
        (ACTION_FOLDER_CHANGED, 'Movida de pasta'),
        (ACTION_CLIENT_ASSOCIATED, 'Cliente associado'),
        (ACTION_CLIENT_REMOVED, 'Cliente removido'),
        (ACTION_PROJECT_ASSOCIATED, 'Projeto associado'),
        (ACTION_PROJECT_REMOVED, 'Projeto removido'),
        (ACTION_VISIBILITY_CHANGED, 'Visibilidade alterada'),
        (ACTION_DELETED, 'Excluída'),
    ]

    # ------------------------------------------------------------------
    # CAMPOS
    # ------------------------------------------------------------------

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    reference = models.ForeignKey(
        'references.Reference',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='history',
        help_text=_(
            'Referência à qual este registro se refere. '
            'NULL quando a referência já foi excluída.'
        ),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reference_history_entries',
        help_text=_('Usuário que executou a ação'),
    )

    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
        db_index=True,
        help_text=_('Ação executada sobre a referência'),
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
        db_table = 'reference_history'
        verbose_name = _('Histórico de Referência')
        verbose_name_plural = _('Históricos de Referência')
        indexes = [
            models.Index(fields=['reference', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['-timestamp']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        ref_label = str(self.reference) if self.reference else 'referência excluída'
        return f"{self.action} · {ref_label}"