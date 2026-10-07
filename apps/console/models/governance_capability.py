"""
Modelo ConsoleGovernanceCapability.

Associação entre Governança e Capability.
Define quais capacidades uma governança possui.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from apps.console.models.governance import ConsoleGovernance
from apps.console.models.capability import ConsoleCapability


class ConsoleGovernanceCapability(models.Model):
    """Associação entre Governança e Capability."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da associação')
    )

    governance = models.ForeignKey(
        ConsoleGovernance,
        on_delete=models.CASCADE,
        related_name='capabilities_relation',
        help_text=_('Governança associada')
    )

    capability = models.ForeignKey(
        ConsoleCapability,
        on_delete=models.CASCADE,
        related_name='governances_relation',
        help_text=_('Capacidade associada')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_('Data de criação')
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_governance_capabilities',
        help_text=_('Usuário que criou a associação')
    )

    class Meta:
        db_table = 'console_governance_capability'
        verbose_name = _('Associação Governança-Capacidade')
        verbose_name_plural = _('Associações Governança-Capacidade')
        constraints = [
            models.UniqueConstraint(
                fields=['governance', 'capability'],
                name='unique_governance_capability'
            ),
        ]
        indexes = [
            models.Index(fields=['governance', 'capability']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['governance', 'capability']

    def __str__(self):
        return f"{self.governance.key} → {self.capability.code}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)