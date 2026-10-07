"""
Modelo PlanFeature.

Relação entre Plan e Feature.

REGRA ARQUITETURAL:
    - Um plano oferece várias features.
    - Uma feature pode pertencer a vários planos.
    - Limites vivem em PlanFeatureLimit (FK para PlanFeature).
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from apps.console.models.plan import Plan
from apps.console.models.feature import Feature


class PlanFeature(models.Model):
    """Associação entre Plan e Feature."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da associação')
    )

    plan = models.ForeignKey(
        Plan,
        on_delete=models.CASCADE,
        related_name='plan_features',
        help_text=_('Plano')
    )

    feature = models.ForeignKey(
        Feature,
        on_delete=models.PROTECT,
        related_name='plan_features',
        help_text=_('Feature associada ao plano')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_plan_features',
        help_text=_('Usuário que criou a associação')
    )

    class Meta:
        db_table = 'console_plan_feature'
        verbose_name = _('Feature de Plano')
        verbose_name_plural = _('Features de Plano')
        constraints = [
            models.UniqueConstraint(
                fields=['plan', 'feature'],
                name='unique_plan_feature',
            ),
        ]
        indexes = [
            models.Index(fields=['plan']),
            models.Index(fields=['feature']),
        ]
        ordering = ['plan', 'feature__name']

    def __str__(self):
        return f"{self.plan.key} → {self.feature.key}"