"""
AIProviderConfigService — leitura e troca da config de IA ativa.

Regras:
    - Singleton: existe uma linha.
    - get_or_create_default cria a linha se não existir.
    - set_provider valida provider 'ai' e model não-vazio.
    - Nunca apaga ProviderLog/UsageRecord.
"""

import logging

from django.conf import settings
from django.db import transaction

from apps.console.models import AIProviderConfig, Provider

logger = logging.getLogger('console')


class AIConfigService:

    @staticmethod
    def get_config():
        return (
            AIProviderConfig.objects
            .select_related('provider', 'updated_by')
            .filter(singleton_key=AIProviderConfig.SINGLETON_KEY)
            .first()
        )

    @staticmethod
    @transaction.atomic
    def get_or_create_default() -> AIProviderConfig:
        existing = AIConfigService.get_config()
        if existing is not None:
            return existing

        provider = (
            Provider.objects
            .filter(category='ai', is_active=True)
            .order_by('key')
            .first()
        )
        if provider is None:
            raise RuntimeError(
                'Nenhum provider de IA ativo cadastrado. '
                'Rode `python manage.py seed_providers`.'
            )

        model = getattr(settings, 'AI_MODEL', 'gpt-4o-mini')

        return AIProviderConfig.objects.create(
            singleton_key=AIProviderConfig.SINGLETON_KEY,
            provider=provider,
            model=model,
            is_active=True,
        )

    @staticmethod
    @transaction.atomic
    def set_provider(
        *,
        provider_key: str,
        model: str,
        actor=None,
        notes: str = '',
    ) -> AIProviderConfig:
        provider = Provider.objects.filter(key=provider_key).first()
        if provider is None:
            raise ValueError(f'Provider "{provider_key}" não existe.')
        if provider.category != 'ai':
            raise ValueError(
                f'Provider "{provider_key}" não é de IA '
                f'(category={provider.category}).'
            )
        if not provider.is_active:
            raise ValueError(
                f'Provider "{provider_key}" está inativo.'
            )

        model = (model or '').strip()
        if not model:
            raise ValueError('O modelo é obrigatório.')

        config = AIConfigService.get_or_create_default()
        previous_provider = config.provider.key
        previous_model = config.model

        config.provider = provider
        config.model = model
        config.is_active = True
        config.notes = notes or ''
        config.updated_by = (
            actor
            if (actor and getattr(actor, 'is_authenticated', False))
            else None
        )
        config.save()

        logger.info(
            'AI config atualizado: %s/%s → %s/%s (by=%s)',
            previous_provider, previous_model,
            provider.key, model,
            getattr(actor, 'email', None) or 'system',
        )
        return config

    @staticmethod
    @transaction.atomic
    def set_active(*, is_active: bool, actor=None) -> AIProviderConfig:
        config = AIConfigService.get_or_create_default()
        config.is_active = bool(is_active)
        config.updated_by = actor
        config.save(update_fields=['is_active', 'updated_by', 'updated_at'])
        return config