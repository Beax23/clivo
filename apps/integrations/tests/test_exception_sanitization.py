"""
Testes de sanitização de exceções.

Garante que nenhuma exceção de integrations carrega tokens
(access_token, refresh_token, authorization code) em message ou context.
"""

import pytest

from apps.integrations.exceptions import (
    ConnectorNotFoundError,
    ConnectionNotFoundError,
    AmbiguousConnectionError,
    InsufficientScopesError,
    RefreshTokenInvalidError,
    ProviderServerError,
)


FORBIDDEN_SUBSTRINGS = [
    'access_token=',
    'refresh_token=',
    'authorization=',
    'client_secret=',
    'Bearer ',
]


class TestExceptionSanitization:

    @pytest.mark.parametrize('exc_class', [
        ConnectorNotFoundError,
        ConnectionNotFoundError,
        AmbiguousConnectionError,
        InsufficientScopesError,
        RefreshTokenInvalidError,
        ProviderServerError,
    ])
    def test_message_does_not_contain_tokens(self, exc_class):
        exc = exc_class('erro genérico')
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in str(exc)

    @pytest.mark.parametrize('exc_class', [
        ConnectorNotFoundError,
        ConnectionNotFoundError,
        AmbiguousConnectionError,
        InsufficientScopesError,
    ])
    def test_context_does_not_contain_tokens(self, exc_class):
        exc = exc_class('erro', context={'provider_key': 'google'})
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in str(exc.context)

    def test_context_is_accessible(self):
        exc = InsufficientScopesError(
            'faltam recursos',
            context={'missing_resources': ['drive.file.read']},
        )
        assert exc.context['missing_resources'] == ['drive.file.read']