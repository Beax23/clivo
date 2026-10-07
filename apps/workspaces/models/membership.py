"""
Modelo WorkspaceMembership.

Associa um usuário a um Workspace com uma Governance do Console.

REGRA ARQUITETURAL:
    A mesma pessoa pode ter governanças diferentes em Workspaces
    diferentes.

    Beatriz
        ├── Workspace A → Proprietário
        ├── Workspace B → Administrador
        └── Workspace C → Membro

    Governance é CONTEXTUAL ao Workspace.
    Governance é DEFINIDA pelo Console.
    Governance é REFERENCIADA por WorkspaceMembership.

O Workspace NÃO possui Governance própria.
O Workspace NÃO possui WorkspaceGovernance / WorkspaceCapability.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from apps.workspaces.models.workspace import Workspace


class WorkspaceMembership(models.Model):
    """Associação entre um usuário, um Workspace e uma Governance."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da associação')
    )

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='memberships',
        help_text=_('Workspace ao qual o usuário pertence')
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workspace_memberships',
        help_text=_('Usuário membro do Workspace')
    )

    governance = models.ForeignKey(
        'console.ConsoleGovernance',
        on_delete=models.PROTECT,
        related_name='workspace_memberships',
        help_text=_(
            'Governança do Console atribuída a este usuário neste Workspace. '
            'Deve ter scope="workspace".'
        )
    )

    joined_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_('Quando o usuário entrou no Workspace')
    )

    last_access_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Último acesso do usuário a este Workspace')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text=_('Data da última atualização')
    )

    class Meta:
        db_table = 'workspace_membership'
        verbose_name = _('Membro do Workspace')
        verbose_name_plural = _('Membros do Workspace')
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'user'],
                name='unique_workspace_user',
            ),
        ]
        indexes = [
            models.Index(fields=['workspace', 'user']),
            models.Index(fields=['user']),
            models.Index(fields=['governance']),
            models.Index(fields=['joined_at']),
        ]
        ordering = ['-joined_at']

    def __str__(self):
        return f"{self.user} @ {self.workspace.name} ({self.governance.key})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.user and not self.user.is_active:
            raise ValidationError({
                'user': _(
                    'Não é possível adicionar um usuário inativo ao Workspace'
                )
            })

        if self.governance and self.governance.scope != 'workspace':
            raise ValidationError({
                'governance': _(
                    'Apenas governanças com scope="workspace" podem ser '
                    'atribuídas a membros de um Workspace.'
                )
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)