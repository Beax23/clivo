"""
Modelo WorkspaceSubscription.

Associa um Workspace a um Plan do Console.

REGRA ARQUITETURAL:
    Plan pertence ao Console.
    Utilização do Plan pertence ao Workspace.

    WorkspaceSubscription é a ponte entre os dois domínios.

CICLO DE VIDA:
    - Criada automaticamente com o Plan is_default=True do Console,
      no momento da criação do Workspace.
    - Pode ser encerrada e substituída por uma nova (upgrade /
      downgrade / ajuste manual). A versão anterior é preservada.
    - No máximo UMA ativa por workspace. Múltiplas inativas são
      permitidas (histórico).

SOBRE A UNICIDADE CONDICIONAL:
    A constraint `unique_active_subscription_per_workspace` garante
    no máximo uma ativa por workspace. NÃO garante que sempre haja
    uma ativa — workspace sem assinatura ativa é estado válido
    (ex: durante uma janela entre trocas, ou antes do backfill).
"""

import uuid
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.workspaces.models.workspace import Workspace


class WorkspaceSubscription(models.Model):

    REASON_INITIAL = 'initial'
    REASON_UPGRADE = 'upgrade'
    REASON_DOWNGRADE = 'downgrade'
    REASON_MANUAL = 'manual'
    REASON_MIGRATION = 'migration'
    REASON_OTHER = 'other'

    REASON_CHOICES = [
        (REASON_INITIAL, 'Criação inicial'),
        (REASON_UPGRADE, 'Upgrade'),
        (REASON_DOWNGRADE, 'Downgrade'),
        (REASON_MANUAL, 'Ajuste manual'),
        (REASON_MIGRATION, 'Migração de dados'),
        (REASON_OTHER, 'Outro'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da assinatura'),
    )

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='subscriptions',
        help_text=_('Workspace assinante'),
    )

    plan = models.ForeignKey(
        'console.Plan',
        on_delete=models.PROTECT,
        related_name='workspace_subscriptions',
        help_text=_('Plano comercial do Console'),
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Se a assinatura está ativa'),
    )

    started_at = models.DateTimeField(
        help_text=_('Início da vigência desta assinatura'),
    )

    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Fim da vigência (opcional)'),
    )

    # ---- Auditoria da troca ----

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='plan_changes_made',
        help_text=_('Usuário que realizou a troca (NULL para criação inicial)'),
    )

    changed_from = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='changed_to',
        help_text=_('Assinatura anterior, quando esta é resultado de uma troca'),
    )

    reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        default=REASON_INITIAL,
        help_text=_('Motivo da criação desta assinatura'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'workspace_subscription'
        verbose_name = _('Assinatura de Workspace')
        verbose_name_plural = _('Assinaturas de Workspace')
        constraints = [
            models.UniqueConstraint(
                fields=['workspace'],
                condition=models.Q(is_active=True),
                name='unique_active_subscription_per_workspace',
            ),
        ]
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
                'ended_at': _('Fim deve ser posterior ao início'),
            })

        if self.is_active and self.ended_at:
            raise ValidationError({
                'is_active': _(
                    'Assinatura ativa não pode ter data de término definida'
                ),
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)