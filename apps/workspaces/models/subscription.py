"""
Modelo WorkspaceSubscription.

Associa um Workspace a um Plan do Console.

REGRA ARQUITETURAL:
    Plan pertence ao Console.
    Utilização do Plan pertence ao Workspace.

    WorkspaceSubscription é a ponte entre os dois domínios.

CICLO DE VIDA (V1):
    - Criado automaticamente com o Plan is_default=True do Console.
    - Sem troca de plano via API na V1.
    - Sem billing / invoice.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.workspaces.models.workspace import Workspace


class WorkspaceSubscription(models.Model):
    """
    Assinatura de um Workspace a um Plan do Console.

    V1: uma subscription ativa por Workspace (OneToOne).
    V2 (futuro): histórico de subscriptions se necessário.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da assinatura')
    )

    workspace = models.OneToOneField(
        Workspace,
        on_delete=models.CASCADE,
        related_name='subscription',
        help_text=_('Workspace assinante')
    )

    plan = models.ForeignKey(
        'console.Plan',
        on_delete=models.PROTECT,
        related_name='workspace_subscriptions',
        help_text=_('Plano comercial do Console')
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Se a assinatura está ativa')
    )

    started_at = models.DateTimeField(
        help_text=_('Início da vigência desta assinatura')
    )

    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Fim da vigência (opcional)')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'workspace_subscription'
        verbose_name = _('Assinatura de Workspace')
        verbose_name_plural = _('Assinaturas de Workspace')
        indexes = [
            models.Index(fields=['workspace', 'is_active']),
            models.Index(fields=['plan']),
            models.Index(fields=['started_at']),
        ]
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.workspace.name} → {self.plan.name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.ended_at and self.started_at and self.ended_at < self.started_at:
            raise ValidationError({
                'ended_at': _('Fim deve ser posterior ao início')
            })

        if self.is_active and self.ended_at:
            raise ValidationError({
                'is_active': _(
                    'Assinatura ativa não pode ter data de término definida'
                )
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)