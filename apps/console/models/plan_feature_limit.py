"""
Modelo PlanFeatureLimit.

Define quanto de cada métrica uma Feature permite dentro de um plano.

Exemplo:
    Plan=Pro
        Feature=Intelligence
            ai.credits = 10.000 / monthly
            intelligence.analysis = 500 / monthly

REGRA ARQUITETURAL:
    - A mesma Feature pode ter limites diferentes em cada plano.
    - O limite vive aqui, NÃO em Feature.
    - O limite é sempre contra uma UsageMetric do catálogo.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.console.models.plan_feature import PlanFeature
from apps.console.models.usage import UsageMetric


class PlanFeatureLimit(models.Model):
    """Limite de uso de uma métrica dentro de uma Feature de um Plano."""

    PERIOD_CHOICES = [
        ('monthly', 'Mensal'),
        ('current', 'Atual'),
        ('lifetime', 'Vitalício'),
    ]

    BEHAVIOR_CHOICES = [
        ('hard_limit', 'Bloquear ao atingir'),
        ('soft_limit', 'Avisar ao atingir'),
        ('overage_allowed', 'Permitir excedente'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único do limite')
    )

    plan_feature = models.ForeignKey(
        PlanFeature,
        on_delete=models.CASCADE,
        related_name='limits',
        help_text=_('Feature do plano à qual este limite pertence')
    )

    metric = models.ForeignKey(
        UsageMetric,
        on_delete=models.PROTECT,
        related_name='plan_feature_limits',
        help_text=_('Métrica limitada')
    )

    limit_value = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_('Valor do limite. NULL significa ilimitado.')
    )

    period = models.CharField(
        max_length=20,
        choices=PERIOD_CHOICES,
        default='monthly',
        help_text=_('Período de reset/aferição')
    )

    behavior = models.CharField(
        max_length=20,
        choices=BEHAVIOR_CHOICES,
        default='hard_limit',
        help_text=_('Comportamento ao atingir o limite')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'console_plan_feature_limit'
        verbose_name = _('Limite de Feature')
        verbose_name_plural = _('Limites de Feature')
        constraints = [
            models.UniqueConstraint(
                fields=['plan_feature', 'metric'],
                name='unique_plan_feature_metric_limit',
            ),
        ]
        indexes = [
            models.Index(fields=['plan_feature']),
            models.Index(fields=['metric']),
        ]
        ordering = ['plan_feature', 'metric__key']

    def __str__(self):
        limit = 'ilimitado' if self.limit_value is None else self.limit_value
        return f"{self.plan_feature} · {self.metric.key} = {limit}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.limit_value is not None and self.limit_value < 0:
            raise ValidationError({
                'limit_value': _('O limite não pode ser negativo')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)