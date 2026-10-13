"""
Models de Provider, ProviderConnection e ProviderContract.

Separação conceitual:
    Provider            → quem fornece o recurso (OpenAI, Backblaze B2, Resend)
    ProviderConnection  → como o Clivo acessa o provider (Production, Test)
    ProviderContract    → o que o Clivo contratou com o provider

REGRA ARQUITETURAL:
    Provider NÃO determina Plan. Plan referencia UsageMetric, nunca Provider.
    Contract é sobre a economia do CLIVO, não sobre o que o Workspace recebe.

SOBRE `included_storage_bytes`:
    Capacidade de armazenamento associada a este contrato, em bytes.

    É uma configuração OPERACIONAL, cadastrada manualmente pelo Console.
    NÃO é lida automaticamente da API do provider — o Backblaze B2, por
    exemplo, não expõe o "Daily Storage Cap" via API S3-compatible. O
    operador vê o cap no console web do B2 (Caps & Alerts) e cadastra
    o valor aqui.

    Semântica de NULL:
        NULL = "teto operacional não cadastrado para este contrato".
        NÃO significa "ilimitado". O sistema nunca presume capacidade
        infinita a partir de NULL — apenas ausência de dado.

    Tipos e propósito:
        - É um número em BYTES (nunca GB, nunca MB).
        - Serve para o Console mostrar "quanto o Clivo contratou no B2".
        - NÃO determina o orçamento operacional do Clivo (isso vive em
          StorageBudget) nem a quota de um plano (isso vive em
          PlanFeatureLimit). São três grandezas distintas.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class Provider(models.Model):
    """
    Empresa/serviço externo que o Clivo utiliza.

    Exemplos:
        OpenAI, Backblaze B2, Resend, Stripe, Render, Neon, Sentry, etc.

    Não possui preço, plano ou limite. Apenas identifica o fornecedor.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único do provider')
    )

    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text=_('Chave estável (ex: "openai", "backblaze_b2", "resend")')
    )

    name = models.CharField(
        max_length=100,
        help_text=_('Nome exibido (ex: "OpenAI")')
    )

    category = models.SlugField(
        max_length=50,
        blank=True,
        help_text=_(
            'Categoria informativa (ex: "ai", "storage", "email", "infra"). '
            'Não determina comportamento — é apenas para organização visual.'
        )
    )

    description = models.TextField(
        blank=True,
        help_text=_('Descrição do provider')
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Se o provider está atualmente em uso pelo Clivo')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_('Data de criação')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text=_('Data da última atualização')
    )

    class Meta:
        db_table = 'console_provider'
        verbose_name = _('Provider')
        verbose_name_plural = _('Providers')
        indexes = [
            models.Index(fields=['key']),
            models.Index(fields=['category']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.key:
            raise ValidationError({'key': _('A chave é obrigatória')})
        if not self.key.islower():
            raise ValidationError({
                'key': _('A chave deve ser em minúsculas')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProviderConnection(models.Model):
    """
    Como o Clivo acessa um Provider.

    Um mesmo provider pode ter múltiplas conexões (Production, Test).

    REGRA DE SEGURANÇA:
        `config` armazena APENAS metadados não-secretos
        (cloud_name, region, project_id).

        Credenciais reais NUNCA são armazenadas aqui — apenas uma
        `credential_ref` que aponta para o secret manager.
    """

    ENVIRONMENT_CHOICES = [
        ('test', 'Test'),
        ('production', 'Production'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da conexão')
    )

    provider = models.ForeignKey(
        Provider,
        on_delete=models.PROTECT,
        related_name='connections',
        help_text=_('Provider associado')
    )

    name = models.CharField(
        max_length=100,
        help_text=_('Nome da conexão (ex: "Clivo Production")')
    )

    environment = models.CharField(
        max_length=20,
        choices=ENVIRONMENT_CHOICES,
        default='production',
        help_text=_('Ambiente da conexão')
    )

    credential_ref = models.CharField(
        max_length=255,
        blank=True,
        help_text=_(
            'Referência ao secret manager (ex: "vault://clivo/openai/prod"). '
            'NUNCA armazenar credenciais em texto puro aqui.'
        )
    )

    config = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            'Metadados NÃO-secretos (ex: {"cloud_name": "clivo-prod"}). '
            'NUNCA armazenar API keys aqui.'
        )
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Se a conexão está ativa')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'console_provider_connection'
        verbose_name = _('Conexão de Provider')
        verbose_name_plural = _('Conexões de Provider')
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'name', 'environment'],
                name='unique_provider_connection'
            ),
        ]
        indexes = [
            models.Index(fields=['provider', 'environment']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['provider__name', 'name']

    def __str__(self):
        return f"{self.provider.name} · {self.name} ({self.environment})"


class ProviderContract(models.Model):
    """
    Contrato/capacidade que o Clivo contratou com um Provider.

    Exemplos:
        OpenAI        → budget US$ 500/mês
        Backblaze B2  → 500 GB storage
        Resend        → 100.000 emails/mês

    REGRA IMPORTANTE:
        Este contrato é sobre a economia do CLIVO com o fornecedor.
        NÃO determina o que um Workspace recebe — isso é Plan.

    SOBRE `included_storage_bytes`:
        Teto operacional de armazenamento associado a este contrato,
        em BYTES. Cadastrado manualmente pelo operador.

        Por que manual e não automático:
            A API S3-compatible do Backblaze B2 (única exposta para
            integração programática) NÃO devolve o "Daily Storage Cap"
            da conta. Esse valor vive apenas no console web do B2,
            em "Caps & Alerts". Não há endpoint para lê-lo.

            Cadastrar aqui significa: "o operador viu o cap no console
            do B2 e registrou no Clivo". O valor fica auditável (quem
            cadastrou, quando) e permite reconciliar com o uso físico
            que o `sync_b2_usage` mede.

        Semântica:
            NULL = teto operacional não cadastrado. NÃO significa
            ilimitado. O sistema nunca presume capacidade infinita
            a partir de NULL.

        Não confundir com:
            StorageBudget.total_budget_bytes  → orçamento do Clivo
                                                 (decisão operacional
                                                 independente do B2)
            PlanFeatureLimit.limit_value      → quota por workspace,
                                                 derivada do plano
    """

    BILLING_PERIOD_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
        ('one_time', 'One Time'),
        ('custom', 'Custom'),
    ]

    CURRENCY_CHOICES = [
        ('BRL', 'BRL'),
        ('USD', 'USD'),
        ('EUR', 'EUR'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único do contrato')
    )

    provider = models.ForeignKey(
        Provider,
        on_delete=models.PROTECT,
        related_name='contracts',
        help_text=_('Provider do contrato')
    )

    connection = models.ForeignKey(
        ProviderConnection,
        on_delete=models.PROTECT,
        related_name='contracts',
        null=True,
        blank=True,
        help_text=_(
            'Conexão associada (opcional). Um contrato pode ser '
            'puramente comercial e não estar ligado a uma conexão específica.'
        )
    )

    name = models.CharField(
        max_length=100,
        help_text=_('Nome do contrato (ex: "Production")')
    )

    external_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text=_(
            'Referência externa (ex: "org_abc123", "CLD-2026-001")'
        )
    )

    billing_period = models.CharField(
        max_length=20,
        choices=BILLING_PERIOD_CHOICES,
        default='monthly',
        help_text=_('Período de cobrança')
    )

    fixed_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Custo fixo contratado (opcional)')
    )

    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='BRL',
        help_text=_('Moeda do custo')
    )

    included_storage_bytes = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_(
            'Teto operacional de armazenamento associado a este contrato, '
            'em bytes. Cadastrado manualmente — a API S3 do Backblaze B2 '
            'não expõe o Daily Storage Cap. NULL = não cadastrado '
            '(NÃO significa ilimitado).'
        )
    )

    started_at = models.DateField(
        help_text=_('Data de início do contrato')
    )

    ends_at = models.DateField(
        null=True,
        blank=True,
        help_text=_('Data de término do contrato (opcional)')
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Se o contrato está ativo')
    )

    notes = models.TextField(
        blank=True,
        help_text=_('Observações internas')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'console_provider_contract'
        verbose_name = _('Contrato de Provider')
        verbose_name_plural = _('Contratos de Provider')
        indexes = [
            models.Index(fields=['provider', 'is_active']),
            models.Index(fields=['started_at']),
            models.Index(fields=['ends_at']),
        ]
        ordering = ['provider__name', '-started_at']

    def __str__(self):
        return f"{self.provider.name} · {self.name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        # Coerência connection ↔ provider
        if self.connection and self.connection.provider_id != self.provider_id:
            raise ValidationError({
                'connection': _(
                    'A conexão selecionada pertence a outro provider.'
                )
            })

        # Datas
        if self.ends_at and self.started_at and self.ends_at < self.started_at:
            raise ValidationError({
                'ends_at': _('Fim deve ser posterior ao início')
            })

        # Custo
        if self.fixed_cost is not None and self.fixed_cost < 0:
            raise ValidationError({
                'fixed_cost': _('O custo fixo não pode ser negativo')
            })

        # Capacidade
        if (
            self.included_storage_bytes is not None
            and self.included_storage_bytes < 0
        ):
            raise ValidationError({
                'included_storage_bytes': _(
                    'O teto de armazenamento não pode ser negativo.'
                )
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)