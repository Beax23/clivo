"""
Service para Provider, ProviderConnection e ProviderContract.

CRUD simples. Sem regra de negócio complexa na V1.
"""

from typing import Optional, List

from apps.console.models import (
    Provider,
    ProviderConnection,
    ProviderContract,
)


class ProviderService:
    """Gerenciamento de providers do Clivo."""

    @staticmethod
    def get_by_key(key: str) -> Optional[Provider]:
        try:
            return Provider.objects.get(key=key)
        except Provider.DoesNotExist:
            return None

    @staticmethod
    def get_or_create(
        key: str,
        name: str,
        category: str = '',
        description: str = '',
    ) -> tuple:
        provider, created = Provider.objects.get_or_create(
            key=key,
            defaults={
                'name': name,
                'category': category,
                'description': description,
            },
        )
        return provider, created

    @staticmethod
    def list_active() -> List[Provider]:
        return list(Provider.objects.filter(is_active=True))

    @staticmethod
    def get_connection(provider: Provider, name: str, environment: str):
        return ProviderConnection.objects.filter(
            provider=provider,
            name=name,
            environment=environment,
        ).first()

    @staticmethod
    def get_or_create_connection(
        provider: Provider,
        name: str,
        environment: str = 'production',
        credential_ref: str = '',
        config: Optional[dict] = None,
    ) -> tuple:
        connection, created = ProviderConnection.objects.get_or_create(
            provider=provider,
            name=name,
            environment=environment,
            defaults={
                'credential_ref': credential_ref,
                'config': config or {},
            },
        )
        return connection, created

    @staticmethod
    def get_or_create_contract(
        provider: Provider,
        name: str,
        started_at,
        connection: Optional[ProviderConnection] = None,
        billing_period: str = 'monthly',
        fixed_cost=None,
        currency: str = 'BRL',
        external_reference: str = '',
        notes: str = '',
    ) -> tuple:
        contract, created = ProviderContract.objects.get_or_create(
            provider=provider,
            name=name,
            defaults={
                'connection': connection,
                'started_at': started_at,
                'billing_period': billing_period,
                'fixed_cost': fixed_cost,
                'currency': currency,
                'external_reference': external_reference,
                'notes': notes,
            },
        )
        return contract, created