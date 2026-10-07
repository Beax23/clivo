"""
Modelo UsageRecord.

Registra o consumo real de um provider pela Clivo.

REGRA ARQUITETURAL:
    UsageRecord NÃO é billing.
    É telemetria econômica de infraestrutura.

    A criação de UsageRecord deve ocorrer via `UsageRecordService`,
    nunca diretamente por API pública. O Console APENAS OBSERVA.

NOTA (workspace_id):
    `workspace_id` é UUIDField solto nesta fase, porque `workspaces`
    ainda não existe. Quando ele existir, uma migration converterá
    em ForeignKey preservando os valores.

NOTA (quantity):
    DecimalField permite frações (GB, segundos, horas, tokens fracionários).
    Para contagens inteiras (tokens, emails, requests), use valores inteiros.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.console.models.provider import Provider, ProviderConnection
from apps.console.models.usage import UsageMetric


class UsageRecord(models.Model):
    """
    Registro de consumo de uma métrica, por um provider, num instante.

    Duas naturezas de uso:
        - volume: quanto foi consumido da métrica (quantity)
        - custo:  quanto isso representa em moeda (estimated_cost)

    O custo é calculado no momento da criação via CostService,
    a partir do ProviderPricing vigente. Pode ser recalculado depois.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único do registro')
    )

    provider = models.ForeignKey(
        Provider,
        on_delete=models.PROTECT,
        related_name='usage_records',
        help_text=_('Provider associado')
    )

    connection = models.ForeignKey(
        ProviderConnection,
        on_delete=models.PROTECT,
        related_name='usage_records',
        null=True,
        blank=True,
        help_text=_('Conexão usada (opcional)')
    )

    metric = models.ForeignKey(
        UsageMetric,
        on_delete=models.PROTECT,
        related_name='usage_records',
        help_text=_('Métrica consumida')
    )

    workspace_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            'ID do Workspace associado (temporariamente UUIDField, '
            'virará FK quando `workspaces` existir).'
        )
    )

    occurred_at = models.DateTimeField(
        db_index=True,
        help_text=_('Quando o consumo ocorreu')
    )

    quantity = models.DecimalField(
        max_digits=24,
        decimal_places=8,
        help_text=_(
            'Quantidade consumida (unidade da métrica). '
            'Decimal permite frações (GB, segundos, horas).'
        )
    )

    unit = models.CharField(
        max_length=50,
        help_text=_('Unidade (ex: "token", "byte", "email")')
    )

    request_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_(
            'ID da requisição. Quando fornecido, atua como chave de '
            'idempotência: dois registros com o mesmo request_id são '
            'considerados duplicata.'
        )
    )

    operation = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Operação que originou o consumo (ex: "briefing.interpretation")')
    )

    model = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Modelo/recurso específico (ex: "gpt-5.6")')
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=_('Metadados adicionais (não-secretos)')
    )

    estimated_cost = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        default=0,
        help_text=_('Custo estimado no momento da criação')
    )

    currency = models.CharField(
        max_length=3,
        default='USD',
        help_text=_('Moeda do custo estimado')
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='success',
        help_text=_('Status do registro')
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'console_usage_record'
        verbose_name = _('Registro de Uso')
        verbose_name_plural = _('Registros de Uso')
        indexes = [
            models.Index(fields=['provider', 'occurred_at']),
            models.Index(fields=['metric', 'occurred_at']),
            models.Index(fields=['workspace_id', 'occurred_at']),
            models.Index(fields=['operation']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'request_id'],
                condition=models.Q(request_id__gt=''),
                name='unique_usage_record_provider_request',
            ),
        ]
        ordering = ['-occurred_at']

    def __str__(self):
        return f"{self.provider.name} · {self.metric.key} · {self.quantity} {self.unit}"