"""
Modelo ProviderPricing.

Representa o preço unitário que a Clivo paga a um Provider por uma
métrica específica, dentro de um contrato específico.

Separação conceitual:
    Contract  → o que a Clivo contratou
    Pricing   → quanto custa cada unidade de consumo

REGRA ARQUITETURAL:
    ProviderPricing NÃO define preço de cliente.
    Preço de cliente é Plan → PlanFeature → PlanFeatureLimit.

    ProviderPricing é sobre a economia interna da Clivo.

Resumo da cadeia comercial (do lado do cliente):

    Plan
        └── PlanFeature
                └── PlanFeatureLimit
                        └── UsageMetric
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.console.models.provider import Provider, ProviderContract
from apps.console.models.usage import UsageMetric


class ProviderPricing(models.Model):
    """
    Preço por unidade de uma métrica dentro de um contrato.

    Exemplos:
        OpenAI / GPT-5.6 input     → $X / 1M tokens
        Cloudinary / Storage       → $X / GB
        Resend / Emails            → $X / 1.000 emails

    O `pricing_model` determina como o custo é calculado a partir
    da `quantity` consumida.
    """

    PRICING_MODEL_CHOICES = [
        ('unit', 'Unit'),        # quantity × unit_price
        ('tiered', 'Tiered'),    # faixas de consumo (não implementado na V1)
        ('flat', 'Flat'),        # custo fixo independente de quantidade
        ('minimum', 'Minimum'),  # max(calculated, minimum_charge)
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
        help_text=_('Identificador único do pricing')
    )

    provider = models.ForeignKey(
        Provider,
        on_delete=models.PROTECT,
        related_name='pricings',
        help_text=_('Provider ao qual este pricing pertence')
    )

    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.PROTECT,
        related_name='pricings',
        null=True,
        blank=True,
        help_text=_(
            'Contrato associado (opcional). Se nulo, aplica-se a '
            'qualquer contrato ativo do provider.'
        )
    )

    metric = models.ForeignKey(
        UsageMetric,
        on_delete=models.PROTECT,
        related_name='provider_pricings',
        help_text=_('Métrica à qual este preço se aplica')
    )

    identifier = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text=_(
            'Identificador específico dentro do provider '
            '(ex: "gpt-5.6-input"). Deixe vazio para pricing genérico.'
        )
    )

    pricing_model = models.CharField(
        max_length=20,
        choices=PRICING_MODEL_CHOICES,
        default='unit',
        help_text=_('Modelo de precificação')
    )

    unit_price = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        default=0,
        help_text=_(
            'Preço por unidade (ex: 0.000015 USD por token). '
            'Use 0 para pricing flat (usa apenas minimum_charge).'
        )
    )

    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='USD',
        help_text=_('Moeda do preço')
    )

    minimum_charge = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_(
            'Cobrança mínima (aplicada em pricing_model=minimum).'
        )
    )

    included_quantity = models.DecimalField(
        max_digits=24,
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_(
            'Franquia incluída antes de cobrar (em unidades da métrica).'
        )
    )

    starts_at = models.DateTimeField(
        help_text=_('Início da vigência deste preço')
    )

    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Fim da vigência (opcional)')
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Se o pricing está vigente')
    )

    notes = models.TextField(
        blank=True,
        help_text=_('Observações internas')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'console_provider_pricing'
        verbose_name = _('Preço de Provider')
        verbose_name_plural = _('Preços de Provider')
        indexes = [
            models.Index(fields=['provider', 'metric', 'is_active']),
            models.Index(fields=['contract']),
            models.Index(fields=['starts_at', 'ends_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'metric', 'identifier', 'starts_at'],
                name='unique_pricing_provider_metric_identifier_starts',
            ),
        ]
        ordering = ['provider__name', 'metric__key', '-starts_at']

    def __str__(self):
        ident = f" ({self.identifier})" if self.identifier else ''
        return f"{self.provider.name} · {self.metric.key}{ident} = {self.unit_price} {self.currency}"

    def clean(self):
        from django.core.exceptions import ValidationError

        # Valida coerência provider ↔ contract
        if self.contract and self.contract.provider_id != self.provider_id:
            raise ValidationError({
                'contract': _(
                    'O contrato selecionado pertence a outro provider. '
                    'Contract e Provider devem ser coerentes.'
                )
            })

        # Contract inativo não pode sustentar pricing ativo
        if self.is_active and self.contract and not self.contract.is_active:
            raise ValidationError({
                'contract': _(
                    'Não é possível vincular pricing ativo a um contrato inativo.'
                )
            })

        # Valores monetários
        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({
                'unit_price': _('O preço não pode ser negativo')
            })

        if self.minimum_charge is not None and self.minimum_charge < 0:
            raise ValidationError({
                'minimum_charge': _('A cobrança mínima não pode ser negativa')
            })

        if self.included_quantity is not None and self.included_quantity < 0:
            raise ValidationError({
                'included_quantity': _('A franquia incluída não pode ser negativa')
            })

        # Datas
        if self.ends_at and self.starts_at and self.ends_at < self.starts_at:
            raise ValidationError({
                'ends_at': _('Fim deve ser posterior ao início')
            })

        # Sobreposição de vigência para a mesma combinação lógica
        # (provider, metric, identifier, contract) — apenas quando ativo.
        if self.is_active and self.starts_at:
            from django.db.models import Q

            overlap_qs = (
                ProviderPricing.objects
                .filter(
                    provider=self.provider,
                    metric=self.metric,
                    identifier=self.identifier or '',
                    contract=self.contract,
                    is_active=True,
                )
                .exclude(pk=self.pk)
            )

            # Sobreposição: existe outro pricing cujo intervalo
            # [starts_at, ends_at] intersecta com o deste.
            #
            # Interseção: other.starts_at < self.ends_at (ou self sem ends)
            #          E  other.ends_at > self.starts_at (ou other sem ends)

            if self.ends_at:
                overlap_qs = overlap_qs.filter(starts_at__lt=self.ends_at)
            # Se self não tem ends_at, qualquer other com starts >= self.starts
            # já está sobreposto — não filtramos por starts_at aqui.

            overlap_qs = overlap_qs.filter(
                Q(ends_at__isnull=True) | Q(ends_at__gt=self.starts_at)
            )

            if overlap_qs.exists():
                raise ValidationError({
                    'starts_at': _(
                        'Existe outro pricing ativo com vigência sobreposta '
                        'para a mesma combinação '
                        '(provider, metric, identifier, contract).'
                    )
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)