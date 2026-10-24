"""
Testes de `GoogleConnector.refresh` e `GoogleConnector.revoke`.

Cobrem:
    - refresh: sucesso, rotação de refresh_token, expiração nova.
    - refresh: invalid_grant → RefreshTokenInvalidError.
    - refresh: falha de rede / 5xx → RefreshTransientError.
    - refresh: sem credenciais → IntegrationConfigurationError.
    - revoke: sucesso (200), já revogado (400), 5xx (best-effort).
    - revoke: falha de rede (best-effort).
    - revoke: sem tokens → não faz chamada.

Nenhuma chamada real ao Google. Mock de `google.auth` e de `httpx`.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
from google.auth.exceptions import RefreshError

from apps.integrations.exceptions import (
    IntegrationConfigurationError,
    RefreshTokenInvalidError,
    RefreshTransientError,
)
from apps.integrations.providers.google.connector import GoogleConnector


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def connector():
    return GoogleConnector()


@pytest.fixture(autouse=True)
def fake_google_credentials(settings):
    """
    Injeta credenciais falsas. Sem isso, `_build_client_config`
    levanta IntegrationConfigurationError antes de qualquer teste.
    """
    settings.INTEGRATIONS_GOOGLE_CLIENT_ID = 'test-client-id'
    settings.INTEGRATIONS_GOOGLE_CLIENT_SECRET = 'test-client-secret'


def _make_mock_credentials(
    token='new-access-token',
    refresh_token='rotated-refresh-token',
    expires_in_seconds=3600,
    scopes=None,
    refresh_error=None,
):
    """
    Constrói um mock de `google.oauth2.credentials.Credentials`
    que se comporta como o real depois de um `refresh()`.
    """
    if scopes is None:
        scopes = ['https://www.googleapis.com/auth/drive.readonly']

    credentials = MagicMock()
    credentials.token = token
    credentials.refresh_token = refresh_token
    credentials.expiry = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    ).replace(tzinfo=None)
    credentials.scopes = scopes

    if refresh_error is not None:
        credentials.refresh.side_effect = refresh_error
    else:
        credentials.refresh.return_value = None

    return credentials


# =========================================================================
# REFRESH
# =========================================================================

class TestRefresh:

    def test_refresh_success(self, connector):
        """Caminho feliz: refresh devolve um access_token novo."""
        mock_creds = _make_mock_credentials()

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleCredentials',
            return_value=mock_creds,
        ):
            result = connector.refresh(refresh_token='old-refresh-token')

        assert result.access_token == 'new-access-token'
        assert result.refresh_token == 'rotated-refresh-token'
        assert result.expires_at is not None
        assert result.expires_at.tzinfo is not None  # tz-aware
        assert 'drive.file.read' in result.provider_metadata[
            'granted_resources'
        ]
        assert result.provider_metadata['source'] == 'refresh'

    def test_refresh_preserves_refresh_token_when_not_rotated(
        self, connector,
    ):
        """
        O Google normalmente NÃO devolve um refresh_token novo.
        Nesse caso, o connector devolve o token que foi passado.
        """
        mock_creds = _make_mock_credentials(
            refresh_token=None,  # Google não devolveu novo
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleCredentials',
            return_value=mock_creds,
        ):
            result = connector.refresh(refresh_token='same-refresh-token')

        assert result.refresh_token == 'same-refresh-token'

    def test_refresh_identity_fields_are_empty(self, connector):
        """
        Refresh NÃO devolve userinfo. Os campos de identidade
        devem vir vazios.
        """
        mock_creds = _make_mock_credentials()

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleCredentials',
            return_value=mock_creds,
        ):
            result = connector.refresh(refresh_token='rt')

        assert result.external_account_id == ''
        assert result.external_account_email == ''
        assert result.external_account_display_name == ''
        assert result.external_account_avatar_url is None

    def test_refresh_invalid_grant_raises_refresh_token_invalid(
        self, connector,
    ):
        """`invalid_grant` do Google → RefreshTokenInvalidError."""
        mock_creds = _make_mock_credentials(
            refresh_error=RefreshError('invalid_grant: Token has been expired or revoked.'),
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleCredentials',
            return_value=mock_creds,
        ):
            with pytest.raises(RefreshTokenInvalidError) as exc_info:
                connector.refresh(refresh_token='rt')

        assert exc_info.value.context['provider_key'] == 'google'

    def test_refresh_invalid_client_raises_refresh_token_invalid(
        self, connector,
    ):
        """`invalid_client` também é permanente."""
        mock_creds = _make_mock_credentials(
            refresh_error=RefreshError('invalid_client: Unauthorized'),
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleCredentials',
            return_value=mock_creds,
        ):
            with pytest.raises(RefreshTokenInvalidError):
                connector.refresh(refresh_token='rt')

    def test_refresh_network_error_raises_transient(self, connector):
        """Erro de rede → RefreshTransientError."""
        mock_creds = _make_mock_credentials(
            refresh_error=RefreshError('Connection reset by peer'),
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleCredentials',
            return_value=mock_creds,
        ):
            with pytest.raises(RefreshTransientError):
                connector.refresh(refresh_token='rt')

    def test_refresh_5xx_raises_transient(self, connector):
        """5xx do Google → transitório."""
        mock_creds = _make_mock_credentials(
            refresh_error=RefreshError('503 Service Unavailable'),
        )

        with patch(
            'apps.integrations.providers.google.connector.'
            'GoogleCredentials',
            return_value=mock_creds,
        ):
            with pytest.raises(RefreshTransientError):
                connector.refresh(refresh_token='rt')

    def test_refresh_without_credentials_raises_config_error(
        self, connector, settings,
    ):
        """Sem Client ID → IntegrationConfigurationError."""
        settings.INTEGRATIONS_GOOGLE_CLIENT_ID = None

        with pytest.raises(IntegrationConfigurationError) as exc_info:
            connector.refresh(refresh_token='rt')

        assert exc_info.value.context['missing'] == 'client_id'


# =========================================================================
# REVOKE
# =========================================================================

class TestRevoke:

    def test_revoke_success(self, connector):
        """Revogação com 200 → sem exceção."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch('httpx.post', return_value=mock_response) as mock_post:
            connector.revoke(
                access_token='at',
                refresh_token='rt',
            )

        # Duas chamadas: uma para refresh_token, outra para access_token.
        assert mock_post.call_count == 2

    def test_revoke_already_revoked_400(self, connector):
        """
        400 (token inválido / já revogado) NÃO é erro para
        revogação.
        """
        mock_response = MagicMock()
        mock_response.status_code = 400

        with patch('httpx.post', return_value=mock_response):
            # Não deve levantar.
            connector.revoke(access_token='at', refresh_token='rt')

    def test_revoke_5xx_is_best_effort(self, connector):
        """5xx do Google → loga mas não levanta."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch('httpx.post', return_value=mock_response):
            # Não deve levantar.
            connector.revoke(access_token='at', refresh_token='rt')

    def test_revoke_network_error_is_best_effort(self, connector):
        """Erro de rede → loga mas não levanta."""
        with patch(
            'httpx.post',
            side_effect=httpx.ConnectError('connection refused'),
        ):
            # Não deve levantar.
            connector.revoke(access_token='at', refresh_token='rt')

    def test_revoke_without_refresh_token_only_revokes_access(
        self, connector,
    ):
        """Sem refresh_token, só revoga o access_token (1 chamada)."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch('httpx.post', return_value=mock_response) as mock_post:
            connector.revoke(access_token='at', refresh_token=None)

        assert mock_post.call_count == 1

    def test_revoke_without_tokens_does_nothing(self, connector):
        """Sem tokens, não faz chamada nenhuma."""
        with patch('httpx.post') as mock_post:
            connector.revoke(access_token='', refresh_token=None)

        mock_post.assert_not_called()