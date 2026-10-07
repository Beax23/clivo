"""
Modelos de Plan.

Plan é o pacote comercial vendido pela Clivo.

Separação conceitual:
    Plan          → o pacote comercial (Starter, Pro, Enterprise)
    PlanFeature   → quais Features aquele plano possui
    PlanFeatureLimit → quanto daquela Feature o plano permite

REGRA ARQUITETURAL:
    Plan NÃO conhece Provider.
    Plan NÃO conhece Capability.
    Plan NÃO tem seed.
    Plan NÃO tem is_system.

    Todo plano é criado pelo operador via Console UI.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class Plan(models.Model):
    """
    Pacote comercial do Clivo.

    Exemplos: Starter, Pro, Enterprise.
    """

    BILLING_PERIOD_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
        ('lifetime', 'Lifetime'),
        ('custom', 'Custom'),
    ]

    CURRENCY_CHOICES = [
        ('BRL', 'BRL'),
        ('USD', 'USD'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único do plano')
    )

    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text=_('Chave estável (gerada automaticamente a partir do nome)')
    )

    name = models.CharField(
        max_length=100,
        help_text=_('Nome exibido (ex: "Starter", "Pro")')
    )

    description = models.TextField(
        blank=True,
        help_text=_('Descrição comercial do plano')
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_('Preço do plano')
    )

    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='BRL',
        help_text=_('Moeda do preço')
    )

    billing_period = models.CharField(
        max_length=20,
        choices=BILLING_PERIOD_CHOICES,
        default='monthly',
        help_text=_('Período de cobrança')
    )

    default_trial_days = models.PositiveIntegerField(
        default=0,
        help_text=_('Sugestão comercial de trial em dias')
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Se o plano está disponível para novas assinaturas')
    )

    is_public = models.BooleanField(
        default=True,
        help_text=_('Se o plano é visível publicamente para escolha')
    )

    is_default = models.BooleanField(
        default=False,
        help_text=_(
            'Plano inicial. Novos Workspaces começam automaticamente neste plano. '
            'Apenas um plano pode ser inicial.'
        )
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_plans',
        help_text=_('Usuário que criou o plano')
    )

    class Meta:
        db_table = 'console_plan'
        verbose_name = _('Plano')
        verbose_name_plural = _('Planos')
        constraints = [
            models.UniqueConstraint(
                fields=['is_default'],
                condition=models.Q(is_default=True),
                name='unique_default_plan',
            ),
        ]
        indexes = [
            models.Index(fields=['key']),
            models.Index(fields=['is_active', 'is_public']),
            models.Index(fields=['is_default']),
            models.Index(fields=['price']),
        ]
        ordering = ['price', 'name']

    def __str__(self):
        return f"{self.name} ({self.currency} {self.price})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.key:
            raise ValidationError({'key': _('A chave é obrigatória')})
        if not self.key.islower():
            raise ValidationError({
                'key': _('A chave deve ser em minúsculas')
            })
        if self.price is not None and self.price < 0:
            raise ValidationError({
                'price': _('O preço não pode ser negativo')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def workspaces_count(self) -> int:
        """
        Quantidade de workspaces usando este plano.

        Como `workspaces` ainda não existe, retorna 0.
        Quando o app nascer, este método será reescrito para:
            WorkspaceSubscription.objects.filter(plan=self).count()
        """
        return 0