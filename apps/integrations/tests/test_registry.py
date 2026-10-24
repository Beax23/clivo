"""
Testes do ProviderRegistry.
"""

import pytest

from apps.integrations.exceptions import ConnectorNotFoundError
from apps.integrations.providers.registry import (
    DuplicateConnectorError,
    ProviderRegistry,
)


class _FakeConnector:
    def __init__(self, key):
        self.key = key


@pytest.fixture(autouse=True)
def clean_registry():
    ProviderRegistry.clear()
    yield
    ProviderRegistry.clear()


class TestProviderRegistry:

    def test_register_and_get(self):
        connector = _FakeConnector('fake')
        ProviderRegistry.register(connector)
        assert ProviderRegistry.get('fake') is connector

    def test_register_duplicate_raises(self):
        ProviderRegistry.register(_FakeConnector('fake'))
        with pytest.raises(DuplicateConnectorError):
            ProviderRegistry.register(_FakeConnector('fake'))

    def test_register_duplicate_with_override(self):
        c1 = _FakeConnector('fake')
        c2 = _FakeConnector('fake')
        ProviderRegistry.register(c1)
        ProviderRegistry.register(c2, override=True)
        assert ProviderRegistry.get('fake') is c2

    def test_get_missing_raises(self):
        with pytest.raises(ConnectorNotFoundError):
            ProviderRegistry.get('missing')

    def test_all_keys(self):
        ProviderRegistry.register(_FakeConnector('a'))
        ProviderRegistry.register(_FakeConnector('b'))
        assert set(ProviderRegistry.all_keys()) == {'a', 'b'}