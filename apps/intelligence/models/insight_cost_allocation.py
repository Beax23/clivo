"""
Alocação de custo de uma execução de IA aos containers/insights
que ela produziu.

REGRA ARQUITETURAL
------------------
`UsageRecord` (em `console`) registra o custo REAL da chamada ao
provedor. Este modelo registra a PARCELA desse custo atribuída a
cada `InsightItem` produzido, segundo uma regra de rateio explícita.

Separação de responsabilidades:
    - console.UsageRecord   → quanto foi cobrado pelo provedor.
    - InsightCostAllocation → como esse custo se distribui entre
                              os insights gerados.

A regra de rateio é determinística e documentada em
`CostAllocationService.allocate_for_run()`. Este modelo apenas
persiste o resultado.

Semântica dos campos:
    - `allocated_cost = None`   → custo desconhecido (não foi possível
                                  calcular, nem por rateio). O chamador
                                  deve tratar como "indisponível", nunca
                                  como zero.
    - `is_estimated = True`     → o valor é resultado de rateio, não
                                  de uma chamada individual. O campo
                                  `allocation_rule` documenta a regra.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class InsightCostAllocation(models.Model):

    RULE_SINGLE_INSIGHT = 'single_insight'
    RULE_EQUAL_SPLIT = 'equal_split'
    RULE_PROPORTIONAL_TOKENS = 'proportional_tokens'

    RULE_CHOICES = [
        (RULE_SINGLE_INSIGHT, 'Um único insight na execução'),
        (RULE_EQUAL_SPLIT, 'Divisão igual entre insights'),
        (RULE_PROPORTIONAL_TOKENS, 'Proporcional a tokens estimados'),
    ]

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False,
    )

    insight = models.ForeignKey(
        'intelligence.InsightItem',
        on_delete=models.CASCADE,
        related_name='cost_allocations',
    )

    usage_record_id = models.UUIDField(
        db_index=True,
        help_text=_(
            'ID do UsageRecord (console) que representa a chamada. '
            'Armazenado como UUID para não criar FK cross-app.'
        ),
    )

    allocated_cost = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_(
            'Parcela do custo atribuída a este insight. NULL = '
            'desconhecido (não confundir com zero).'
        ),
    )

    currency = models.CharField(
        max_length=3,
        blank=True,
        default='',
        help_text=_('Moeda do custo alocado. Vazia quando desconhecido.'),
    )

    is_estimated = models.BooleanField(
        default=True,
        help_text=_(
            'True quando o valor foi obtido por rateio, não por uma '
            'cobrança individual.'
        ),
    )

    allocation_rule = models.CharField(
        max_length=40,
        choices=RULE_CHOICES,
        help_text=_('Regra determinística usada para calcular a parcela.'),
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'intelligence_insight_cost_allocation'
        verbose_name = _('Alocação de Custo')
        verbose_name_plural = _('Alocações de Custo')
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['insight', 'usage_record_id'],
                name='unique_cost_allocation_per_insight_usage_record',
            ),
        ]
        indexes = [
            models.Index(fields=['insight', '-created_at']),
            models.Index(fields=['usage_record_id']),
        ]

    def __str__(self):
        value = (
            f'{self.allocated_cost} {self.currency}'
            if self.allocated_cost is not None
            else 'desconhecido'
        )
        return f'{self.insight_id} · {value} ({self.allocation_rule})'