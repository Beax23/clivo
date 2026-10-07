"""
Modelo ConsoleGovernance.

Governança do Console — Control Plane da Clivo.

Uma governança é um papel administrativo que pode ser atribuído
a um membro do Console via `ConsoleMembership`, ou a um membro
de um Workspace via `WorkspaceMembership`.

REGRA ARQUITETURAL:
    Governanças NÃO carregam contexto de domínio (workspace, etc).
    São apenas papéis administrativos da Clivo.

    O campo `scope` determina onde a governança pode ser usada:
        scope='console'   → apenas ConsoleMembership
        scope='workspace' → apenas WorkspaceMembership

REGRA DE EDIÇÃO:
    `is_protected=True` significa que a governança NÃO pode ser excluída.
    NÃO significa que ela não pode ser editada.

    Governanças de sistema PODEM ter `name` e `description` editados.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class ConsoleGovernance(models.Model):
    """Governança do Console — Control Plane da Clivo."""

    SCOPE_CHOICES = [
        ('console', 'Console'),
        ('workspace', 'Workspace'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da governança')
    )

    key = models.CharField(
        max_length=50,
        unique=True,
        help_text=_('Chave estável para referência interna (ex: "proprietario")')
    )

    name = models.CharField(
        max_length=100,
        help_text=_('Nome exibido da governança')
    )

    description = models.TextField(
        blank=True,
        help_text=_('Descrição da governança')
    )

    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default='console',
        db_index=True,
        help_text=_(
            'Onde esta governança pode ser atribuída. '
            '"console" → ConsoleMembership. '
            '"workspace" → WorkspaceMembership.'
        )
    )

    is_system = models.BooleanField(
        default=False,
        help_text=_(
            'Governança nativa do sistema. '
            'Não pode ser excluída. Pode ser editada.'
        )
    )

    is_protected = models.BooleanField(
        default=False,
        help_text=_(
            'Governança protegida. '
            'Não pode ser excluída. Pode ser editada.'
        )
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_('Data de criação')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text=_('Data da última atualização')
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_governances',
        help_text=_('Usuário que criou a governança')
    )

    class Meta:
        db_table = 'console_governance'
        verbose_name = _('Governança do Console')
        verbose_name_plural = _('Governanças do Console')
        indexes = [
            models.Index(fields=['key']),
            models.Index(fields=['scope']),
            models.Index(fields=['is_system', 'is_protected']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.scope})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.is_system and not self.is_protected:
            raise ValidationError({
                'is_protected': _('Governanças de sistema devem ser protegidas')
            })

        if not self.key or not self.key.islower() or ' ' in self.key:
            raise ValidationError({
                'key': _('A chave deve ser em minúsculas, sem espaços')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Impede exclusão de governanças protegidas ou de sistema.

        Edição de `name`/`description` continua permitida.
        """
        from django.core.exceptions import ValidationError

        if self.is_protected:
            raise ValidationError(
                _('Não é possível excluir uma governança protegida')
            )
        if self.is_system:
            raise ValidationError(
                _('Não é possível excluir uma governança de sistema')
            )

        super().delete(*args, **kwargs)