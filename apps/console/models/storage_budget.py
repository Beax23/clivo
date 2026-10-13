"""
Modelos de orçamento operacional de armazenamento do Clivo.

============================================================================
REGRA ARQUITETURAL
============================================================================

O `StorageBudget` é o ORÇAMENTO OPERACIONAL do Clivo. É uma decisão
comercial/operacional, não uma consequência automática de infraestrutura.

    ProviderContract.included_storage_bytes  → o que o Clivo contratou
                                                com o fornecedor externo
    StorageBudget.total_budget_bytes         → o que o Clivo decide
                                                disponibilizar aos clientes
    PlanFeatureLimit.limit_value             → quota de um workspace
                                                dentro de um plano

São três grandezas independentes. Cadastrar um teto no B2 NÃO popula
o orçamento do Clivo automaticamente. Definir um orçamento NÃO cria
quotas em planos.

============================================================================
SINGLETON REAL
============================================================================

`StorageBudget` é singleton por construção: existe UMA linha com
`singleton_key='default'`. A constraint `unique=True` no campo impede
duas linhas. Não é um "singleton por convenção" — é garantido pelo
banco.

Toda mutação passa pelo `StorageBudgetService`, que usa
`select_for_update` dentro de transação. Duas requisições concorrentes
não conseguem gravar ao mesmo tempo.

============================================================================
HISTÓRICO
============================================================================

`StorageBudgetChange` é APPEND-ONLY. Cada alteração do orçamento grava
uma linha com:

    - valores anteriores (`previous_*`)
    - valores novos (`new_*`)
    - responsável (`changed_by`)
    - motivo (`reason`)
    - timestamp (`created_at`)

O histórico não é editado nem apagado. Se um orçamento foi alterado por
engano, o correto é gravar uma nova alteração revertendo o valor —
mantém a cadeia auditável.

============================================================================
RESERVA OPERACIONAL
============================================================================

`reserve_percent` é o percentual do orçamento total que o Clivo NÃO
aloca a clientes. Serve para margem de segurança operacional:

    - arquivos temporários e órfãos
    - versões antigas em providers com versionamento
    - crescimento inesperado antes de ajustar o plano
    - margem para aumento de custo do provider

Default: 20%. Ajustável pelo Console.

    allocatable_bytes = total_budget_bytes × (100 - reserve_percent) / 100

============================================================================
POLÍTICA DE ALOCAÇÃO
============================================================================

    strict       → a soma das quotas prometidas nunca excede allocatable.
                   Toda nova quota é validada contra o disponível.
                   Bloqueia upgrade de plano se não couber.

    controlled   → permite sobrealocação. A validação de quota NÃO é
                   bloqueante; o Console avisa, mas aplica.

Default: `strict`. Trocar para `controlled` é decisão explícita do
operador, registrada no histórico.

A política é aplicada pela Etapa 3 (quotas de plano). O StorageBudget
apenas ARMAZENA a política escolhida. Ele NÃO bloqueia nada por si só —
quem bloqueia é o serviço que valida quota contra orçamento.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class StorageBudget(models.Model):
    """
    Orçamento operacional de armazenamento do Clivo.

    Singleton. Uma única linha, identificada por
    `singleton_key='default'`.
    """

    POLICY_STRICT = 'strict'
    POLICY_CONTROLLED = 'controlled'

    POLICY_CHOICES = [
        (POLICY_STRICT, _('Estrita')),
        (POLICY_CONTROLLED, _('Controlada')),
    ]

    SINGLETON_KEY = 'default'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único do orçamento'),
    )

    singleton_key = models.CharField(
        max_length=20,
        unique=True,
        default=SINGLETON_KEY,
        editable=False,
        help_text=_(
            'Chave de singleton. Sempre "default". Garante no banco que '
            'existe uma única linha de orçamento.'
        ),
    )

    total_budget_bytes = models.BigIntegerField(
        help_text=_(
            'Orçamento operacional total do Clivo, em bytes. Decisão '
            'comercial/operacional, independente do teto do provider.'
        ),
    )

    reserve_percent = models.PositiveSmallIntegerField(
        default=20,
        help_text=_(
            'Percentual do orçamento reservado para operação (10–40 '
            'recomendado). O restante é alocável a workspaces.'
        ),
    )

    allocation_policy = models.CharField(
        max_length=20,
        choices=POLICY_CHOICES,
        default=POLICY_STRICT,
        help_text=_(
            'Política de alocação de quotas. "strict" bloqueia alocação '
            'acima do disponível. "controlled" permite sobrealocação '
            'com aviso.'
        ),
    )

    updated_at = models.DateTimeField(auto_now=True)

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_storage_budgets',
        help_text=_('Último usuário que alterou o orçamento'),
    )

    class Meta:
        db_table = 'console_storage_budget'
        verbose_name = _('Orçamento de Armazenamento')
        verbose_name_plural = _('Orçamentos de Armazenamento')

    def __str__(self):
        return (
            f"StorageBudget(total={self.total_budget_bytes} B, "
            f"reserve={self.reserve_percent}%, "
            f"policy={self.allocation_policy})"
        )

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.singleton_key != self.SINGLETON_KEY:
            raise ValidationError({
                'singleton_key': _(
                    'O singleton_key deve ser sempre "default".'
                )
            })

        if self.total_budget_bytes is not None and self.total_budget_bytes < 0:
            raise ValidationError({
                'total_budget_bytes': _(
                    'O orçamento total não pode ser negativo.'
                )
            })

        if self.reserve_percent is None or not (0 <= self.reserve_percent <= 100):
            raise ValidationError({
                'reserve_percent': _(
                    'A reserva deve estar entre 0 e 100.'
                )
            })

        if self.allocation_policy not in dict(self.POLICY_CHOICES):
            raise ValidationError({
                'allocation_policy': _('Política inválida.')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # DERIVADOS
    # ------------------------------------------------------------------

    @property
    def allocatable_bytes(self) -> int:
        """
        Bytes que o Clivo pode alocar a workspaces.

            allocatable = total × (100 - reserve_percent) / 100

        A operação é feita em inteiro para evitar erro de ponto
        flutuante. Arredonda para baixo.
        """
        total = int(self.total_budget_bytes or 0)
        reserve = int(self.reserve_percent or 0)
        return (total * (100 - reserve)) // 100


class StorageBudgetChange(models.Model):
    """
    Registro histórico de alterações do orçamento.

    APPEND-ONLY. Nunca editado, nunca apagado.

    Se uma alteração foi feita por engano, o correto é gravar uma nova
    alteração revertendo o valor. Assim a cadeia fica auditável.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    budget = models.ForeignKey(
        StorageBudget,
        on_delete=models.PROTECT,
        related_name='changes',
        help_text=_('Orçamento alterado'),
    )

    previous_total_bytes = models.BigIntegerField(
        help_text=_('Orçamento total antes da alteração'),
    )
    new_total_bytes = models.BigIntegerField(
        help_text=_('Orçamento total depois da alteração'),
    )

    previous_reserve_percent = models.PositiveSmallIntegerField(
        help_text=_('Reserva antes da alteração'),
    )
    new_reserve_percent = models.PositiveSmallIntegerField(
        help_text=_('Reserva depois da alteração'),
    )

    previous_allocation_policy = models.CharField(
        max_length=20,
        help_text=_('Política antes da alteração'),
    )
    new_allocation_policy = models.CharField(
        max_length=20,
        help_text=_('Política depois da alteração'),
    )

    reason = models.TextField(
        blank=True,
        help_text=_('Justificativa da alteração'),
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='storage_budget_changes',
        help_text=_('Usuário que alterou'),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'console_storage_budget_change'
        verbose_name = _('Alteração de Orçamento')
        verbose_name_plural = _('Alterações de Orçamento')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['budget', '-created_at']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return (
            f"Budget change "
            f"{self.previous_total_bytes} → {self.new_total_bytes} "
            f"({self.created_at:%Y-%m-%d %H:%M})"
        )