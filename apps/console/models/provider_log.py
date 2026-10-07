"""
Modelo ProviderLog.

Registra cada chamada operacional a um provider externo.

Diferente de UsageRecord:
    - UsageRecord  → "consumimos X unidades da métrica Y"
    - ProviderLog  → "chamamos o provider com estes parâmetros e obtivemos este resultado"

REGRA ARQUITETURAL:
    ProviderLog é observabilidade operacional do Console.
    Não confundir com AuditLog (que é sobre ações administrativas).

    A criação de ProviderLog deve ocorrer via `ProviderLogService`,
    nunca diretamente por API pública. O Console APENAS OBSERVA.

NOTA (workspace_id):
    Mesmo padrão de UsageRecord — UUIDField solto nesta fase.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.console.models.provider import Provider, ProviderConnection


class ProviderLog(models.Model):
    """
    Log operacional de uma chamada a um provider externo.

    Exemplo:
        Provider: OpenAI
        Operation: briefing.interpretation
        Model: gpt-5.6
        Status: success
        Latency: 1840ms
        Input: 12430 tokens
        Output: 2108 tokens
        Cost: 0.83 BRL
    """

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('timeout', 'Timeout'),
        ('rate_limited', 'Rate Limited'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único do log')
    )

    provider = models.ForeignKey(
        Provider,
        on_delete=models.PROTECT,
        related_name='logs',
        help_text=_('Provider chamado')
    )

    connection = models.ForeignKey(
        ProviderConnection,
        on_delete=models.PROTECT,
        related_name='logs',
        null=True,
        blank=True,
        help_text=_('Conexão usada (opcional)')
    )

    workspace_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            'ID do Workspace que originou a chamada '
            '(temporariamente UUIDField, virará FK).'
        )
    )

    occurred_at = models.DateTimeField(
        db_index=True,
        help_text=_('Quando a chamada ocorreu')
    )

    operation = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Operação (ex: "briefing.interpretation")')
    )

    model = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Modelo/recurso usado (ex: "gpt-5.6")')
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='success',
        help_text=_('Resultado da chamada')
    )

    latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_('Latência em milissegundos')
    )

    input_units = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_('Unidades de entrada (ex: input tokens)')
    )

    output_units = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_('Unidades de saída (ex: output tokens)')
    )

    estimated_cost = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_('Custo estimado da chamada')
    )

    currency = models.CharField(
        max_length=3,
        blank=True,
        default='USD',
        help_text=_('Moeda do custo estimado')
    )

    request_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_('ID da requisição (opcional)')
    )

    correlation_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_('ID de correlação (opcional)')
    )

    error_message = models.TextField(
        blank=True,
        help_text=_('Mensagem de erro (se houver)')
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=_('Metadados adicionais (não-secretos)')
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'console_provider_log'
        verbose_name = _('Log de Provider')
        verbose_name_plural = _('Logs de Provider')
        indexes = [
            models.Index(fields=['provider', 'occurred_at']),
            models.Index(fields=['status', 'occurred_at']),
            models.Index(fields=['workspace_id', 'occurred_at']),
            models.Index(fields=['operation']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-occurred_at']

    def __str__(self):
        return f"{self.provider.name} · {self.operation} · {self.status}"