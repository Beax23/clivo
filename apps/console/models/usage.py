"""
Modelo UsageMetric.

Cataloga as métricas que podem ser limitadas/medidas pela plataforma.

REGRA ARQUITETURAL:
    UsageMetric é catálogo puro. Não é CRUD manual do Console na V1.
    Novas métricas entram via seed (enquanto os domínios ainda não
    existem). Futuramente, cada domínio declarará suas métricas
    via `capabilities.py`-like pattern.

Uso da métrica:
    UsageMetric é referenciada por:
        - PlanFeatureLimit (limite comercial por plano)
        - ProviderPricing  (preço de custo por provider)
        - UsageRecord      (telemetria de consumo)
"""

import uuid
import re

from django.db import models
from django.utils.translation import gettext_lazy as _


# Formato permitido para key de métrica: <segmento>.<segmento>[.<segmento>]
# Segmentos aceitam a-z, 0-9 e underscore. Separados por ponto.
METRIC_KEY_RE = re.compile(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$')


class UsageMetric(models.Model):
    """
    Métrica que o Clivo pode medir e limitar.

    Duas naturezas:
        - recorded: o domínio grava registros de consumo
                    (ex: ai.credits, email.sent)
        - derived:  o domínio sabe responder "quanto está agora"
                    (ex: storage.bytes, members.count)

    A natureza NÃO é o tipo de dado — é a origem do valor.
    """

    KIND_CHOICES = [
        ('counter', 'Counter'),   # incrementa com eventos
        ('gauge', 'Gauge'),       # representa estado atual
        ('rate', 'Rate'),         # por unidade de tempo
    ]

    ORIGIN_CHOICES = [
        ('recorded', 'Recorded'),  # domínio grava UsageRecord
        ('derived', 'Derived'),    # domínio responde .count() / .sum()
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da métrica')
    )

    key = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text=_(
            'Chave única da métrica no formato "<domínio>.<recurso>" '
            '(ex: "ai.credits", "storage.bytes", "email.sent")'
        )
    )

    name = models.CharField(
        max_length=150,
        help_text=_('Nome exibido (ex: "AI Credits")')
    )

    unit = models.CharField(
        max_length=50,
        help_text=_(
            'Unidade da métrica (ex: "credit", "byte", "email", "member")'
        )
    )

    kind = models.CharField(
        max_length=20,
        choices=KIND_CHOICES,
        default='counter',
        help_text=_('Tipo de contagem da métrica')
    )

    origin = models.CharField(
        max_length=20,
        choices=ORIGIN_CHOICES,
        default='recorded',
        help_text=_(
            'recorded: o domínio grava UsageRecord. '
            'derived: o domínio responde o estado atual via count/sum.'
        )
    )

    description = models.TextField(
        blank=True,
        help_text=_('Descrição da métrica')
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_(
            'Se a métrica está disponível para uso em '
            'PlanFeatureLimit e ProviderPricing'
        )
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'console_usage_metric'
        verbose_name = _('Métrica de Uso')
        verbose_name_plural = _('Métricas de Uso')
        indexes = [
            models.Index(fields=['key']),
            models.Index(fields=['kind']),
            models.Index(fields=['origin']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['key']

    def __str__(self):
        return f"{self.key} — {self.name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.key:
            raise ValidationError({
                'key': _('A chave é obrigatória')
            })

        if not METRIC_KEY_RE.match(self.key):
            raise ValidationError({
                'key': _(
                    'A chave deve estar no formato "<domínio>.<recurso>" '
                    'com segmentos em minúsculas, sem hífens ou espaços '
                    '(ex: "ai.credits", "storage.bytes")'
                )
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)