"""
Configuração do provider de IA ATIVO para o Console.

Singleton. Existe UMA linha com `singleton_key='default'`. A linha
representa "qual provider/modelo usar quando AICallService.call() é
invocado sem provider_key explícito".

NÃO é o mesmo que `Provider` (catálogo) nem `ProviderContract`
(economia). É a decisão operacional do operador: "estamos usando
OpenAI gpt-4o-mini agora".

A troca NÃO apaga histórico de `ProviderLog` nem de `UsageRecord`.
O histórico continua apontando para o provider/modelo usados no
momento da chamada. Trocar aqui só afeta as próximas chamadas.

O `Provider` referenciado PRECISA ter `category='ai'` — validado
em `clean()`. Providers de storage/email são rejeitados.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class AIProviderConfig(models.Model):
    """
    Config ativa de IA. Singleton.

    Campos:
        provider    → Provider do catálogo (categoria 'ai').
        model       → Nome do modelo (ex: "gpt-4o-mini").
        is_active   → Se True, chamadas sem `provider_key` usam esta.
        notes       → Observações do operador.
        updated_by  → Quem fez a última troca.
    """

    SINGLETON_KEY = 'default'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    singleton_key = models.CharField(
        max_length=20,
        unique=True,
        default=SINGLETON_KEY,
        editable=False,
        help_text=_('Sempre "default". Garante no banco o singleton.'),
    )

    provider = models.ForeignKey(
        'console.Provider',
        on_delete=models.PROTECT,
        related_name='ai_configs',
        help_text=_('Provider de IA ativo (ex: openai, gemini).'),
    )

    model = models.CharField(
        max_length=100,
        help_text=_('Modelo padrão (ex: gpt-4o-mini, gemini-1.5-flash).'),
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Se True, chamadas sem provider_key usam esta config.'),
    )

    notes = models.TextField(
        blank=True,
        default='',
        help_text=_('Observações do operador (não afeta execução).'),
    )

    updated_at = models.DateTimeField(auto_now=True)

    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_ai_configs',
    )

    class Meta:
        db_table = 'console_ai_provider_config'
        verbose_name = _('Configuração de IA')
        verbose_name_plural = _('Configurações de IA')

    def __str__(self):
        return (
            f'AI: {self.provider.key}/{self.model} '
            f'(active={self.is_active})'
        )

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.singleton_key != self.SINGLETON_KEY:
            raise ValidationError({
                'singleton_key': 'Deve ser "default".',
            })

        if not self.model or not self.model.strip():
            raise ValidationError({
                'model': 'O modelo é obrigatório.',
            })

        if self.provider and self.provider.category != 'ai':
            raise ValidationError({
                'provider': (
                    f'Provider "{self.provider.key}" não é de IA '
                    f'(category={self.provider.category}).'
                ),
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)