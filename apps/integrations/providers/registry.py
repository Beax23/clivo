"""
ProviderRegistry — registro em memória dos connectors de provider.

Populado em AppConfig.ready(). NÃO faz I/O externo.

DUPLICIDADE:
    - register() sem override levanta DuplicateConnectorError.
    - Tests chamam register(override=True) para mockar.
"""

from apps.integrations.exceptions import IntegrationError


class DuplicateConnectorError(IntegrationError):
    """
    Tentativa de registrar connector com chave já existente sem override.
    """


class ProviderRegistry:
    """
    Registro em memória. Não é thread-safe por design; registro
    acontece em ready(), antes de qualquer request.
    """

    _connectors: dict = {}

    @classmethod
    def register(cls, connector, *, override: bool = False) -> None:
        """
        Registra um connector.

        Se a chave já existe e override=False, levanta DuplicateConnectorError.
        Se override=True, sobrescreve silenciosamente (uso em testes).
        """
        key = connector.key
        if key in cls._connectors and not override:
            raise DuplicateConnectorError(
                f'Connector "{key}" já registrado. '
                f'Use override=True apenas em testes.',
                context={'provider_key': key},
            )
        cls._connectors[key] = connector

    @classmethod
    def get(cls, key: str):
        from apps.integrations.exceptions import ConnectorNotFoundError
        connector = cls._connectors.get(key)
        if connector is None:
            raise ConnectorNotFoundError(
                f'Connector "{key}" não registrado.',
                context={'provider_key': key},
            )
        return connector

    @classmethod
    def all_keys(cls) -> list:
        return list(cls._connectors.keys())

    @classmethod
    def clear(cls) -> None:
        """Uso em testes."""
        cls._connectors.clear()